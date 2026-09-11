"""Authorization-code bootstrap and noninteractive refresh with private token storage."""

import json
import os
import secrets
import tempfile
import time
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from dotenv import load_dotenv

from src.config import Settings
from src.http import SpotifyError, json_object, request

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
SCOPES = ["user-top-read", "user-read-recently-played", "user-read-private"]


class TokenManager:
    def __init__(self, settings: Settings, session=None):
        self.settings = settings
        self.session = session or requests.Session()

    def _read(self) -> dict:
        try:
            data = json.loads(self.settings.token_cache.read_text())
        except FileNotFoundError:
            return {}
        except (ValueError, UnicodeError):
            raise SpotifyError(
                "Invalid token cache; run python -m src.auth again"
            ) from None
        if not isinstance(data, dict):
            raise SpotifyError("Token cache must be an object")
        return data

    def _save(self, data: dict) -> None:
        path = self.settings.token_cache
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".spotify-token-")
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(data, stream)
            os.replace(
                temp, path
            )  # mkstemp creates mode 0600; atomic within filesystem
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    def _token_request(self, payload: dict, previous_refresh: str = "") -> dict:
        response = request(
            self.session,
            "POST",
            TOKEN_URL,
            self.settings,
            auth=(self.settings.client_id, self.settings.client_secret),
            data=payload,
        )
        data = json_object(response)
        if not isinstance(data.get("access_token"), str) or not data["access_token"]:
            raise SpotifyError("Token response missing access_token")
        expires = data.get("expires_in")
        if (
            isinstance(expires, bool)
            or not isinstance(expires, (int, float))
            or not 60 < expires <= 86400
        ):
            raise SpotifyError("Token response has invalid expires_in")
        refresh = data.get("refresh_token", previous_refresh)
        if not isinstance(refresh, str) or not refresh:
            raise SpotifyError("Token response missing refresh_token")
        data["refresh_token"] = refresh
        data["obtained_at"] = time.time()
        self._save(data)
        return data

    def get_token(self, *, force_refresh: bool = False) -> str:
        data = self._read()
        try:
            valid = (
                time.time()
                < float(data.get("obtained_at", 0))
                + float(data.get("expires_in", 0))
                - 60
            )
        except (TypeError, ValueError):
            valid = False
        if (
            not force_refresh
            and valid
            and isinstance(data.get("access_token"), str)
            and data["access_token"]
        ):
            return data["access_token"]
        refresh = data.get("refresh_token") or self.settings.refresh_token
        if not isinstance(refresh, str) or not refresh:
            raise SpotifyError(
                "No refresh token; run python -m src.auth before scheduling"
            )
        return self._token_request(
            {"grant_type": "refresh_token", "refresh_token": refresh}, refresh
        )["access_token"]

    def authorize(self, input_fn=input) -> None:
        state = secrets.token_urlsafe(32)
        url = (
            AUTH_URL
            + "?"
            + urlencode(
                {
                    "client_id": self.settings.client_id,
                    "response_type": "code",
                    "redirect_uri": self.settings.redirect_uri,
                    "scope": " ".join(SCOPES),
                    "state": state,
                }
            )
        )
        print(f"Open this URL and authorize Spotify:\n{url}")
        redirect = input_fn(
            "Paste the full redirected URL (the page need not load): "
        ).strip()
        parsed, expected = urlparse(redirect), urlparse(self.settings.redirect_uri)
        if (parsed.scheme, parsed.netloc, parsed.path) != (
            expected.scheme,
            expected.netloc,
            expected.path,
        ):
            raise SpotifyError("Redirect URI mismatch")
        params = parse_qs(parsed.query)
        if params.get("state") != [state]:
            raise SpotifyError("OAuth state mismatch")
        if "error" in params or len(params.get("code", [])) != 1:
            raise SpotifyError("Spotify authorization denied or missing code")
        self._token_request(
            {
                "grant_type": "authorization_code",
                "code": params["code"][0],
                "redirect_uri": self.settings.redirect_uri,
            }
        )
        print("Authorization saved to the private token cache.")


def get_valid_token() -> str:
    """Compatibility entry point for local reporting; never prompts inside ETL."""
    return TokenManager(Settings.from_env()).get_token()


if __name__ == "__main__":
    load_dotenv()
    TokenManager(Settings.from_env()).authorize()
