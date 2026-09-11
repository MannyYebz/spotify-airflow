import pandas as pd

from src.transform import analytics_history as history


def test_legacy_schema_and_duration_provenance():
    old = pd.DataFrame([{"played_at": "2026-09-01T01:00:00+01:00", "duration_min": 2}])
    result = history._normalize_history_schema(old)
    assert list(result.columns) == history.HISTORY_COLUMNS
    assert result.iloc[0]["played_at_utc"] == "2026-09-01T00:00:00Z"
    assert pd.isna(result.iloc[0]["ms_played"])
    assert pd.isna(result.iloc[0]["track_duration_ms"])


def test_history_enriches_duplicate_events(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "HISTORY_DIR", tmp_path / "nested" / "history")
    monkeypatch.setattr(history, "HISTORY_CSV", history.HISTORY_DIR / "history.csv")
    recent = pd.DataFrame(
        [
            {
                "played_at_utc": "2026-09-01T00:00:00Z",
                "track_id": "t",
                "track_duration_ms": 100,
            }
        ]
    )
    exported = pd.DataFrame(
        [
            {
                "played_at_utc": "2026-09-01T00:00:00.000Z",
                "track_id": "t",
                "ms_played": 50,
            }
        ]
    )
    first = history.update_listening_history(recent, exported)
    second = history.update_listening_history(recent, exported)
    assert len(first) == len(second) == 1
    assert (
        second.iloc[0]["track_duration_ms"] == 100 and second.iloc[0]["ms_played"] == 50
    )
