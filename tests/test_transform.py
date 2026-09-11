from copy import deepcopy
from datetime import datetime, timezone

import pytest

from src.transform.normalize import SCHEMAS, normalize
from src.validation import ValidationError, utc_timestamp


def test_recent_normalization(raw):
    table = normalize(raw)
    row = table.to_pylist()[0]
    assert table.schema == SCHEMAS["recently_played"]
    assert row["name"] == "A song"
    assert row["artist_ids"] == ["artist-1"]
    assert row["track_duration_ms"] == 123000
    assert row["ms_played"] is None
    assert row["played_at_utc"] == datetime(2026, 9, 1, 0, 5, tzinfo=timezone.utc)


def test_duplicate_offset_timestamps_same_event(raw):
    duplicate = deepcopy(raw["pages"][0]["items"][0])
    duplicate["played_at"] = "2026-08-31T20:05:00-04:00"
    raw["pages"].append({"items": [duplicate]})
    assert normalize(raw).num_rows == 1
    duplicate["played_at"] = "2026-09-01T00:06:00Z"
    assert normalize(raw).num_rows == 2


def test_interval_boundaries(raw):
    item = raw["pages"][0]["items"][0]
    item["played_at"] = raw["interval_start"]
    assert normalize(raw).num_rows == 1
    item["played_at"] = raw["interval_end"]
    assert normalize(raw).num_rows == 0


@pytest.mark.parametrize("value", [None, "bad", "2026-09-01T00:05:00", 123])
def test_bad_play_timestamp_fails(raw, value):
    raw["pages"][0]["items"][0]["played_at"] = value
    with pytest.raises(ValidationError):
        normalize(raw)


def test_null_optional_fields(raw):
    raw["pages"][0]["items"][0]["track"] = {"id": "t", "artists": None, "album": None}
    row = normalize(raw).to_pylist()[0]
    assert row["name"] is None and row["track_duration_ms"] is None
    assert row["artist_names"] == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("duration_ms", -1),
        ("duration_ms", "100"),
        ("duration_ms", True),
        ("artists", "bad"),
        ("artists", [None]),
        ("album", [1]),
        ("name", 42),
        ("id", ""),
    ],
)
def test_malformed_track_fields(raw, field, value):
    raw["pages"][0]["items"][0]["track"][field] = value
    with pytest.raises(ValidationError):
        normalize(raw)


@pytest.mark.parametrize("track", [None, {"id": None}, {"id": "x", "is_local": True}])
def test_unavailable_tracks_counted_and_skipped(raw, track, caplog):
    raw["pages"][0]["items"][0]["track"] = track
    with caplog.at_level("INFO"):
        assert normalize(raw).num_rows == 0
    assert "unavailable=1" in caplog.text


@pytest.mark.parametrize("dataset", list(SCHEMAS))
def test_empty_schema_matches_nonempty(raw, dataset, track):
    raw["dataset"] = dataset
    raw["pages"] = [{"items": []}]
    empty = normalize(raw)
    assert empty.schema == SCHEMAS[dataset]
    raw["pages"] = [
        {
            "items": [{"track": track, "played_at": "2026-09-01T00:01:00Z"}]
            if dataset == "recently_played"
            else [track]
        }
    ]
    assert normalize(raw).schema == empty.schema


def test_top_tracks_ranks_dedupe_and_limit(raw, track):
    raw["dataset"] = "top_tracks"
    raw["top_limit"] = 3
    raw["pages"] = [{"items": [track, track, {"id": "t2"}, {"id": "t3"}]}]
    rows = normalize(raw).to_pylist()
    assert [r["rank"] for r in rows] == [1, 3]
    assert [r["track_id"] for r in rows] == ["track-1", "t2"]
    assert all(r["time_range"] == "medium_term" for r in rows)


def test_artist_genres_and_dedup(raw):
    raw["dataset"] = "top_artists"
    artist = {"id": "a", "genres": [" rock ", "rock", ""]}
    raw["pages"] = [{"items": [artist, artist]}]
    rows = normalize(raw).to_pylist()
    assert len(rows) == 1 and rows[0]["genres"] == ["rock"]


@pytest.mark.parametrize(
    "patch",
    [
        {"schema_version": 2},
        {"pages": None},
        {"pages": []},
        {"dataset": "other"},
        {"interval_end": "2026-08-01T00:00:00Z"},
    ],
)
def test_invalid_envelope(raw, patch):
    raw.update(patch)
    with pytest.raises(ValidationError):
        normalize(raw)


def test_aware_datetime_and_dst():
    assert utc_timestamp("2026-11-01T01:30:00-04:00") != utc_timestamp(
        "2026-11-01T01:30:00-05:00"
    )
    with pytest.raises(ValidationError):
        utc_timestamp(datetime(2026, 1, 1))


@pytest.mark.parametrize(
    "field,value", [("artists", {}), ("album", []), ("artists", "")]
)
def test_falsey_wrong_nested_types_rejected(raw, field, value):
    raw["pages"][0]["items"][0]["track"][field] = value
    with pytest.raises(ValidationError):
        normalize(raw)


@pytest.mark.parametrize("genres", [{}, "", [1]])
def test_bad_genres_rejected(raw, genres):
    raw["dataset"] = "top_artists"
    raw["pages"] = [{"items": [{"id": "a", "genres": genres}]}]
    with pytest.raises(ValidationError):
        normalize(raw)
