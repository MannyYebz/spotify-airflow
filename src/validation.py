"""Small validation functions for untrusted API and raw-storage payloads."""

from datetime import datetime, timezone


class ValidationError(ValueError):
    pass


def utc_timestamp(value) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise ValidationError("Invalid ISO timestamp") from None
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValidationError("Timestamp must include a timezone")
    return value.astimezone(timezone.utc)


def page_items(page) -> list[dict]:
    if not isinstance(page, dict) or not isinstance(page.get("items"), list):
        raise ValidationError("API page must contain an items array")
    if any(not isinstance(item, dict) for item in page["items"]):
        raise ValidationError("API items must be objects")
    if page.get("next") is not None and not isinstance(page["next"], str):
        raise ValidationError("API next must be a URL or null")
    return page["items"]


def required_id(value, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"Missing or invalid {field}")
    return value.strip()


def optional_text(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError("Expected text or null")
    return value.strip() or None


def optional_int(value):
    if value is None:
        return None
    if type(value) is not int or not 0 <= value <= 2**63 - 1:
        raise ValidationError("Expected nonnegative integer or null")
    return value
