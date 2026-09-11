import json
import stat
import time
from dataclasses import replace
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

import pytest

from src.auth import TokenManager
from src.config import Settings
from src.http import SpotifyError


def test_config_requires_only_execution_secrets(monkeypatch):
    with pytest.raises(ValueError, match="SPOTIFY_CLIENT_ID"):
        Settings.from_env()
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "test")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "private-value")
    assert "private-value" not in repr(Settings.from_env())
    with pytest.raises(ValueError, match="S3_BUCKET"):
        Settings.from_env(require_s3=True)
    monkeypatch.setenv("S3_BUCKET", "test-bucket")
    monkeypatch.setenv("S3_PREFIX", "/listening/")
    assert Settings.from_env(require_s3=True).prefix == "listening"


@pytest.mark.parametrize(
    "field,value",
    [
        ("time_range", "wrong"),
        ("top_limit", 0),
        ("max_pages", 0),
        ("http_attempts", 0),
        ("timeout", float("nan")),
        ("max_retry_wait", -1),
        ("bucket", "s3://bucket"),
        ("prefix", "../../data"),
        ("redirect_uri", "http://example.com"),
    ],
)
def test_invalid_settings(settings, field, value):
    with pytest.raises(ValueError):
        replace(settings, **{field: value}).validate()


def test_cached_access_token_does_not_call_api(settings):
    tokens = TokenManager(settings, Mock())
    tokens._save(
        {"access_token": "cached", "obtained_at": time.time(), "expires_in": 3600}
    )
    assert tokens.get_token() == "cached"
    tokens.session.request.assert_not_called()
    assert stat.S_IMODE(settings.token_cache.stat().st_mode) == 0o600


def test_refresh_retains_or_rotates_token(settings, response):
    session = Mock()
    tokens = TokenManager(settings, session)
    session.request.return_value = response(
        {"access_token": "access", "expires_in": 3600}
    )
    assert tokens.get_token() == "access"
    assert (
        json.loads(settings.token_cache.read_text())["refresh_token"] == "test-refresh"
    )
    session.request.return_value = response(
        {"access_token": "new", "expires_in": 3600, "refresh_token": "rotated"}
    )
    assert tokens.get_token(force_refresh=True) == "new"
    assert json.loads(settings.token_cache.read_text())["refresh_token"] == "rotated"
    tokens.get_token(force_refresh=True)
    assert session.request.call_args.kwargs["data"]["refresh_token"] == "rotated"


def test_no_interactive_auth_in_tasks(settings):
    with pytest.raises(SpotifyError, match="No refresh token"):
        TokenManager(replace(settings, refresh_token=""), Mock()).get_token()


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"access_token": "x"},
        {"access_token": "x", "expires_in": -1},
        {"access_token": "x", "expires_in": True},
        {"access_token": "x", "expires_in": 3600, "refresh_token": 4},
    ],
)
def test_bad_token_response_not_persisted(settings, response, data):
    session = Mock()
    session.request.return_value = response(data)
    with pytest.raises(SpotifyError):
        TokenManager(settings, session).get_token()
    assert not settings.token_cache.exists()


@pytest.mark.parametrize("contents", ["garbage", "[]"])
def test_corrupt_cache_actionable(settings, contents):
    settings.token_cache.write_text(contents)
    with pytest.raises(SpotifyError, match="cache"):
        TokenManager(settings, Mock()).get_token()


def test_oauth_state_mismatch_never_exchanges(settings):
    session = Mock()
    with pytest.raises(SpotifyError, match="state"):
        TokenManager(settings, session).authorize(
            lambda _: settings.redirect_uri + "?code=private&state=wrong"
        )
    session.request.assert_not_called()


def test_oauth_bootstrap(settings, response, capsys):
    session = Mock()
    session.request.return_value = response(
        {
            "access_token": "private-access",
            "refresh_token": "private-refresh",
            "expires_in": 3600,
        }
    )

    def answer(_):
        printed = capsys.readouterr().out
        url = printed.splitlines()[-1]
        state = parse_qs(urlparse(url).query)["state"][0]
        return settings.redirect_uri + f"?code=test-code&state={state}"

    TokenManager(settings, session).authorize(answer)
    output = capsys.readouterr().out
    assert "private-access" not in output and "private-refresh" not in output
    assert (
        session.request.call_args.kwargs["data"]["grant_type"] == "authorization_code"
    )
    assert settings.token_cache.exists()
