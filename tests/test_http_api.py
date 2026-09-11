from dataclasses import replace
from unittest.mock import Mock, call

import pytest
import requests

from src.extract.raw import extract_dataset
from src.http import RetryableSpotifyError, SpotifyError, json_object, request
from src.spotify import BASE_URL, SpotifyClient
from src.validation import ValidationError


@pytest.mark.parametrize("data", [None, [], "text", 2])
def test_non_object_json(response, data):
    with pytest.raises(SpotifyError, match="object"):
        json_object(response(data))


def test_invalid_json(response):
    result = response()
    result.json.side_effect = ValueError("body might contain secrets")
    with pytest.raises(SpotifyError, match="invalid JSON"):
        json_object(result)


@pytest.mark.parametrize(
    "failure", [requests.Timeout(), requests.ConnectionError(), 500, 503, 429]
)
def test_retryable_then_success(settings, response, failure):
    session, sleep = Mock(), Mock()
    session.request.side_effect = [
        response(status=failure, headers={"Retry-After": "3"})
        if isinstance(failure, int)
        else failure,
        response({"ok": True}),
    ]
    result = request(session, "GET", BASE_URL, settings, sleep=sleep)
    assert result.json() == {"ok": True}
    sleep.assert_called_once_with(3 if failure == 429 else 1)
    assert session.request.call_count == 2


def test_exhaustion(settings, response):
    session, sleep = Mock(), Mock()
    session.request.return_value = response(status=503)
    with pytest.raises(RetryableSpotifyError):
        request(session, "GET", BASE_URL, settings, sleep=sleep)
    assert session.request.call_count == 4
    assert sleep.call_args_list == [call(1), call(2), call(4)]


def test_long_rate_limit_is_not_shortened(settings, response):
    session, sleep = Mock(), Mock()
    session.request.return_value = response(status=429, headers={"Retry-After": "900"})
    with pytest.raises(RetryableSpotifyError, match="wait budget"):
        request(session, "GET", BASE_URL, settings, sleep=sleep)
    sleep.assert_not_called()
    assert session.request.call_count == 1


@pytest.mark.parametrize("status", [400, 403, 404, 302])
def test_permanent_error_no_retry(settings, response, status):
    session = Mock()
    session.request.return_value = response(status=status)
    client = SpotifyClient(settings, session, Mock())
    with pytest.raises(SpotifyError, match=str(status)):
        client.get(BASE_URL + "/me")
    assert session.request.call_count == 1


def test_401_refresh_once(settings, response):
    session, tokens = Mock(), Mock()
    session.request.side_effect = [response(status=401), response({"id": "u"})]
    client = SpotifyClient(settings, session, tokens)
    assert client.get(BASE_URL + "/me") == {"id": "u"}
    assert tokens.get_token.call_args_list == [
        call(force_refresh=False),
        call(force_refresh=True),
    ]
    session.request.side_effect = [response(status=401), response(status=401)]
    with pytest.raises(SpotifyError, match="401"):
        client.get(BASE_URL + "/me")


def test_pagination_preserves_query(settings, response):
    session = Mock()
    next_url = BASE_URL + "/me/top/tracks?offset=50&limit=50"
    session.request.side_effect = [
        response({"items": [{"id": "a"}], "next": next_url}),
        response({"items": [{"id": "b"}], "next": None}),
    ]
    client = SpotifyClient(settings, session, Mock())
    pages = client.pages("/me/top/tracks", {"limit": 50})
    assert len(pages) == 2
    assert session.request.call_args.args[1] == next_url
    assert session.request.call_args.kwargs["params"] is None


@pytest.mark.parametrize(
    "page",
    [
        {},
        {"items": None},
        {"items": {}},
        {"items": [None]},
        {"items": [], "next": 1},
        {"items": [], "next": BASE_URL + "/me/top/tracks?offset=1"},
    ],
)
def test_malformed_pages_fail(settings, response, page):
    session = Mock()
    session.request.return_value = response(page)
    with pytest.raises(ValidationError):
        SpotifyClient(settings, session, Mock()).pages("/me/top/tracks", {})


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.test/v1/me/top/tracks?offset=1",
        "https://api.spotify.com@evil.test/v1/me/top/tracks",
        "http://api.spotify.com/v1/me/top/tracks",
        BASE_URL + "/me/top/artists?offset=1",
    ],
)
def test_no_credentials_sent_to_unsafe_next(settings, response, url):
    session = Mock()
    session.request.return_value = response({"items": [{"id": "a"}], "next": url})
    with pytest.raises(ValidationError):
        SpotifyClient(settings, session, Mock()).pages("/me/top/tracks", {})
    assert session.request.call_count == 1


def test_pagination_cycle(settings, response):
    session = Mock()
    session.request.return_value = response(
        {"items": [{}], "next": BASE_URL + "/me/top/tracks"}
    )
    with pytest.raises(ValidationError, match="cycle"):
        SpotifyClient(settings, session, Mock()).pages("/me/top/tracks", {})


def test_page_cap_fails_instead_of_truncating(settings, response):
    session = Mock()
    session.request.return_value = response(
        {"items": [{}], "next": BASE_URL + "/me/top/tracks?offset=1"}
    )
    with pytest.raises(ValidationError, match="MAX_PAGES"):
        SpotifyClient(replace(settings, max_pages=1), session, Mock()).pages(
            "/me/top/tracks", {}
        )


def test_requested_top_limit_stops_pagination(settings, response):
    session = Mock()
    session.request.return_value = response(
        {"items": [{}, {}], "next": BASE_URL + "/me/top/tracks?offset=2"}
    )
    assert (
        len(
            SpotifyClient(settings, session, Mock()).pages(
                "/me/top/tracks", {}, max_items=2
            )
        )
        == 1
    )


@pytest.mark.parametrize(
    "dataset,path",
    [
        ("recently_played", "/me/player/recently-played"),
        ("top_tracks", "/me/top/tracks"),
        ("top_artists", "/me/top/artists"),
    ],
)
def test_extraction_envelope(settings, dataset, path):
    client = Mock(settings=settings)
    client.pages.return_value = [{"items": []}]
    result = extract_dataset(
        client, dataset, "2026-09-01T00:00:00Z", "2026-09-01T00:15:00Z"
    )
    assert result["dataset"] == dataset
    assert result["pages"] == [{"items": []}]
    assert client.pages.call_args.args[0] == path
    if dataset == "recently_played":
        assert client.pages.call_args.args[1]["after"] == 1788220799999


def test_recent_cursor_next(settings, response):
    session = Mock()
    next_url = BASE_URL + "/me/player/recently-played?before=1788220900000&limit=50"
    session.request.side_effect = [
        response({"items": [{}], "next": next_url}),
        response({"items": []}),
    ]
    assert (
        len(
            SpotifyClient(settings, session, Mock()).pages(
                "/me/player/recently-played", {"after": 1}
            )
        )
        == 2
    )
    assert session.request.call_args.args[1] == next_url


def test_retry_after_http_date(settings, response, monkeypatch):
    session, sleep = Mock(), Mock()
    monkeypatch.setattr("src.http.time.time", lambda: 0)
    session.request.side_effect = [
        response(status=429, headers={"Retry-After": "Thu, 01 Jan 1970 00:00:05 GMT"}),
        response({}),
    ]
    request(session, "GET", BASE_URL, settings, sleep=sleep)
    sleep.assert_called_once_with(5)


def test_malformed_retry_after_uses_backoff(settings, response):
    session, sleep = Mock(), Mock()
    session.request.side_effect = [
        response(status=429, headers={"Retry-After": "bad"}),
        response({}),
    ]
    request(session, "GET", BASE_URL, settings, sleep=sleep)
    sleep.assert_called_once_with(1)


def test_network_exhaustion_redacts_underlying_error(settings):
    session = Mock()
    session.request.side_effect = requests.ConnectionError("secret-in-url")
    with pytest.raises(RetryableSpotifyError) as error:
        request(session, "GET", BASE_URL, settings, sleep=Mock())
    assert "secret-in-url" not in str(error.value)
