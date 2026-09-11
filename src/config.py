"""Read configuration at execution time; importing modules never needs secrets."""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class Settings:
    client_id: str = field(repr=False)
    client_secret: str = field(repr=False)
    refresh_token: str = field(default="", repr=False)
    redirect_uri: str = "http://127.0.0.1:9090"
    token_cache: Path = Path(".token_cache.json")
    bucket: str = ""
    prefix: str = "spotify"
    region: str = "us-east-1"
    time_range: str = "medium_term"
    top_limit: int = 50
    max_pages: int = 100
    http_attempts: int = 4
    timeout: float = 30
    max_retry_wait: float = 120

    @classmethod
    def from_env(
        cls, *, require_s3: bool = False, require_spotify: bool = True
    ) -> "Settings":
        def required(name: str) -> str:
            value = os.getenv(name, "").strip()
            if not value:
                raise ValueError(f"{name} is required")
            return value

        settings = cls(
            client_id=required("SPOTIFY_CLIENT_ID") if require_spotify else "",
            client_secret=required("SPOTIFY_CLIENT_SECRET") if require_spotify else "",
            refresh_token=os.getenv("SPOTIFY_REFRESH_TOKEN", ""),
            redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI", cls.redirect_uri),
            token_cache=Path(os.getenv("SPOTIFY_TOKEN_CACHE", ".token_cache.json")),
            bucket=required("S3_BUCKET") if require_s3 else os.getenv("S3_BUCKET", ""),
            prefix=os.getenv("S3_PREFIX", "spotify").strip("/"),
            region=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
            time_range=os.getenv("SPOTIFY_TIME_RANGE", "medium_term"),
            top_limit=int(os.getenv("SPOTIFY_TOP_LIMIT", "50")),
            max_pages=int(os.getenv("SPOTIFY_MAX_PAGES", "100")),
            http_attempts=int(os.getenv("HTTP_ATTEMPTS", "4")),
            timeout=float(os.getenv("HTTP_TIMEOUT", "30")),
            max_retry_wait=float(os.getenv("HTTP_MAX_RETRY_WAIT", "120")),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.time_range not in {"short_term", "medium_term", "long_term"}:
            raise ValueError("Invalid SPOTIFY_TIME_RANGE")
        if not 1 <= self.top_limit <= 1000 or not 1 <= self.max_pages <= 1000:
            raise ValueError("Top limit and max pages must be between 1 and 1000")
        if not 1 <= self.http_attempts <= 10:
            raise ValueError("HTTP_ATTEMPTS must be between 1 and 10")
        if not 0 < self.timeout <= 300 or not 0 < self.max_retry_wait <= 3600:
            raise ValueError("HTTP timeout/retry wait out of range")
        if self.prefix and not re.fullmatch(r"[A-Za-z0-9_/-]+", self.prefix):
            raise ValueError("S3_PREFIX may contain letters, numbers, _, -, and /")
        if self.bucket and not re.fullmatch(
            r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", self.bucket
        ):
            raise ValueError("S3_BUCKET must be a bucket name, not a URI")
        uri = urlparse(self.redirect_uri)
        if (
            not uri.netloc
            or uri.fragment
            or uri.query
            or not (
                uri.scheme == "https"
                or (
                    uri.scheme == "http"
                    and uri.hostname in {"127.0.0.1", "[::1]", "::1"}
                )
            )
        ):
            raise ValueError("Redirect URI must use HTTPS or an HTTP loopback address")
