from unittest.mock import Mock

import pytest

from src.config import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(
        client_id="test-client",
        client_secret="test-secret",
        refresh_token="test-refresh",
        token_cache=tmp_path / "tokens.json",
        bucket="test-bucket",
    )


@pytest.fixture
def response():
    def make(data=None, status=200, headers=None):
        result = Mock(status_code=status, headers=headers or {})
        result.json.return_value = data
        return result

    return make


@pytest.fixture
def track():
    return {
        "id": "track-1",
        "name": " A song ",
        "duration_ms": 123000,
        "artists": [{"id": "artist-1", "name": "Artist"}],
        "album": {"id": "album-1", "name": "Album"},
    }


@pytest.fixture
def raw(track):
    return {
        "schema_version": 1,
        "dataset": "recently_played",
        "interval_start": "2026-09-01T00:00:00Z",
        "interval_end": "2026-09-01T00:15:00Z",
        "extracted_at": "2026-09-01T00:16:00Z",
        "time_range": "medium_term",
        "top_limit": 50,
        "pages": [
            {
                "items": [{"track": track, "played_at": "2026-09-01T00:05:00Z"}],
                "next": None,
            }
        ],
    }


@pytest.fixture(autouse=True)
def isolate_environment(monkeypatch):
    # No credential files, dotenv, instance metadata, or accidental HTTP in tests.
    import os

    import requests

    for key in list(os.environ):
        if key.startswith(("SPOTIFY_", "AWS_", "S3_", "HTTP_")):
            monkeypatch.delenv(key)
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")

    def reject(*args, **kwargs):
        raise AssertionError("Unexpected real HTTP request")

    monkeypatch.setattr(requests.Session, "request", reject)
