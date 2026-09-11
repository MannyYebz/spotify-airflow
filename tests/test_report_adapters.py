from datetime import datetime, timezone
from unittest.mock import Mock

from src.extract import fetch_data


def test_recent_report_keeps_latest_rows(settings, track, monkeypatch):
    monkeypatch.setattr(fetch_data.Settings, "from_env", lambda: settings)
    client = Mock()
    client.pages.return_value = [
        {
            "items": [
                {"track": track, "played_at": "2020-01-01T00:01:00Z"},
                {"track": track, "played_at": "2020-01-01T00:02:00Z"},
            ]
        }
    ]
    client.settings = settings
    monkeypatch.setattr(fetch_data, "SpotifyClient", lambda _: client)
    result = fetch_data.get_recently_played(limit=1)
    client.pages.assert_called_once_with(
        "/me/player/recently-played", {"limit": 1}, max_items=1
    )
    assert list(result.columns) == fetch_data.RECENTLY_PLAYED_COLUMNS
    assert len(result) == 1
    assert datetime.fromisoformat(result.iloc[0]["played_at_utc"]) == datetime(
        2020, 1, 1, 0, 2, tzinfo=timezone.utc
    )


def test_empty_reports_keep_columns(settings, monkeypatch):
    monkeypatch.setattr(fetch_data.Settings, "from_env", lambda: settings)
    client = Mock(settings=settings)
    client.pages.return_value = [{"items": []}]
    monkeypatch.setattr(fetch_data, "SpotifyClient", lambda _: client)
    assert (
        list(fetch_data.get_recently_played().columns)
        == fetch_data.RECENTLY_PLAYED_COLUMNS
    )
    assert "artist" in fetch_data.get_top_tracks().columns
    assert "genres" in fetch_data.get_top_artists().columns
