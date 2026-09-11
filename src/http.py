"""Bounded HTTP retries shared by OAuth and API requests."""

import logging
import time
from email.utils import parsedate_to_datetime

import requests

from src.config import Settings

log = logging.getLogger(__name__)


class SpotifyError(RuntimeError):
    """A permanent Spotify HTTP or protocol failure (no response bodies logged)."""


class RetryableSpotifyError(SpotifyError):
    """Transient failure exhausted local retries; orchestration may retry later."""


def request(
    session, method: str, url: str, settings: Settings, *, sleep=time.sleep, **kwargs
):
    for attempt in range(settings.http_attempts):
        delay = min(2**attempt, settings.max_retry_wait)
        try:
            response = session.request(
                method, url, timeout=settings.timeout, allow_redirects=False, **kwargs
            )
        except (requests.Timeout, requests.ConnectionError):
            if attempt == settings.http_attempts - 1:
                raise RetryableSpotifyError("Spotify connection failed") from None
        else:
            if response.status_code != 429 and response.status_code < 500:
                return response
            if response.status_code == 429:
                value = response.headers.get("Retry-After", "")
                try:
                    delay = max(0, float(value))
                except ValueError:
                    try:
                        delay = max(
                            0, parsedate_to_datetime(value).timestamp() - time.time()
                        )
                    except (ValueError, TypeError, OverflowError):
                        pass
                # Never retry sooner than requested, or hold a worker indefinitely.
                if not 0 <= delay <= settings.max_retry_wait:
                    raise RetryableSpotifyError(
                        "Spotify rate limit exceeds local wait budget"
                    )
            if attempt == settings.http_attempts - 1:
                raise RetryableSpotifyError(
                    f"Spotify HTTP {response.status_code}; retries exhausted"
                )
        log.warning(
            "Retrying Spotify request; attempt=%s wait_seconds=%s", attempt + 1, delay
        )
        sleep(delay)
    raise AssertionError("Unreachable with validated HTTP_ATTEMPTS")


def json_object(response) -> dict:
    if not 200 <= response.status_code < 300:
        raise SpotifyError(f"Spotify HTTP {response.status_code}")
    try:
        data = response.json()
    except ValueError:
        raise SpotifyError("Spotify returned invalid JSON") from None
    if not isinstance(data, dict):
        raise SpotifyError("Spotify response must be a JSON object")
    return data
