"""Spotify HTTP client with safe, bounded pagination and one refresh on 401."""

from urllib.parse import urlparse

import requests

from src.auth import TokenManager
from src.config import Settings
from src.http import json_object, request
from src.validation import ValidationError, page_items

BASE_URL = "https://api.spotify.com/v1"


class SpotifyClient:
    def __init__(self, settings: Settings, session=None, tokens=None):
        self.settings = settings
        self.session = session or requests.Session()
        self.tokens = tokens or TokenManager(settings, self.session)

    def get(self, url: str, params=None) -> dict:
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "api.spotify.com"
            or not parsed.path.startswith("/v1/")
            or parsed.fragment
        ):
            raise ValidationError("Unsafe Spotify URL")
        for refresh in (False, True):
            response = request(
                self.session,
                "GET",
                url,
                self.settings,
                params=params,
                headers={
                    "Authorization": f"Bearer {self.tokens.get_token(force_refresh=refresh)}"
                },
            )
            if response.status_code != 401 or refresh:
                return json_object(response)
        raise AssertionError("Unreachable")

    def pages(
        self, path: str, params: dict, *, max_items: int | None = None
    ) -> list[dict]:
        url = BASE_URL + path
        pages, seen, count = [], set(), 0
        for _ in range(self.settings.max_pages):
            if url in seen:
                raise ValidationError("Spotify pagination cycle")
            seen.add(url)
            page = self.get(url, params=params)
            items = page_items(page)
            pages.append(page)
            count += len(items)
            next_url = page.get("next")
            if not next_url or (max_items is not None and count >= max_items):
                return pages
            if not items:
                raise ValidationError("Empty Spotify page has a next link")
            # Keep pagination on the same endpoint, including cursor query parameters.
            if urlparse(next_url).path != urlparse(BASE_URL + path).path:
                raise ValidationError("Pagination changed endpoint")
            url, params = next_url, None
        raise ValidationError(
            "Spotify exceeded SPOTIFY_MAX_PAGES; refusing partial extraction"
        )
