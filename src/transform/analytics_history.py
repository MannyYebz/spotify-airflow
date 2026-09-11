import json
from pathlib import Path

import pandas as pd

from src.utils.terminal import status

HISTORY_DIR = Path("data/analytics_history")
HISTORY_CSV = HISTORY_DIR / "listening_history.csv"
RECENT_HISTORY_DIR = Path("data/recent_history")
RECENT_HISTORY_CSV = RECENT_HISTORY_DIR / "recent_listening_history.csv"
HISTORY_COLUMNS = [
    "played_at_utc",
    "name",
    "artist",
    "album",
    "track_duration_ms",
    "ms_played",
    "track_id",
]


def _normalize_history_schema(history):
    """Return history in the canonical schema, including safe legacy migration."""
    history = history.copy()
    if "played_at_utc" not in history.columns and "played_at" in history.columns:
        history = history.rename(columns={"played_at": "played_at_utc"})
    elif "played_at" in history.columns:
        history["played_at_utc"] = history["played_at_utc"].fillna(history["played_at"])

    # Legacy duration_min mixed full track length with actual listening time.
    # Its provenance is unknowable, so never promote it into either new field.
    for column in HISTORY_COLUMNS:
        if column not in history.columns:
            history[column] = pd.NA
    timestamps = pd.to_datetime(
        history["played_at_utc"], format="mixed", utc=True, errors="coerce"
    )
    history["played_at_utc"] = timestamps.map(
        lambda value: (
            value.isoformat().replace("+00:00", "Z") if pd.notna(value) else pd.NA
        )
    )
    history["track_duration_ms"] = pd.to_numeric(
        history["track_duration_ms"], errors="coerce"
    ).astype("Int64")
    history["ms_played"] = pd.to_numeric(history["ms_played"], errors="coerce").astype(
        "Int64"
    )
    return history[HISTORY_COLUMNS]


def import_extended_streaming_history(export_dir):
    """Load Spotify's extracted extended-history JSON files into the history CSV."""
    export_dir = Path(export_dir)
    json_files = sorted(export_dir.glob("Streaming_History_*.json"))
    if not json_files:
        status(f"No extended-history JSON files found in {export_dir}")
        return pd.DataFrame(columns=HISTORY_COLUMNS)

    plays = []
    for json_file in json_files:
        with json_file.open(encoding="utf-8") as file:
            records = json.load(file)

        for record in records:
            track_uri = record.get("spotify_track_uri") or ""
            track_name = record.get("master_metadata_track_name")
            if not track_name or not track_uri.startswith("spotify:track:"):
                continue

            plays.append(
                {
                    "played_at_utc": record.get("ts") or None,
                    "name": track_name,
                    "artist": record.get("master_metadata_album_artist_name")
                    or "Unknown",
                    "album": record.get("master_metadata_album_album_name")
                    or "Unknown",
                    "track_duration_ms": None,
                    "ms_played": record.get("ms_played"),
                    "track_id": track_uri.removeprefix("spotify:track:"),
                }
            )

    imported = pd.DataFrame(plays, columns=HISTORY_COLUMNS)
    status(f"Loaded {len(imported):,} plays from Spotify extended history")
    return imported


def save_recent_listening_history(recently_played):
    """Replace the recent-history CSV with the latest Spotify snapshot."""
    RECENT_HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    if recently_played is None or recently_played.empty:
        recent_history = pd.DataFrame(columns=HISTORY_COLUMNS)
    else:
        recent_history = _normalize_history_schema(recently_played)

    recent_history.to_csv(RECENT_HISTORY_CSV, index=False)
    status(f"Saved {RECENT_HISTORY_CSV} · {len(recent_history):,} recent plays")
    return recent_history


def update_listening_history(recently_played, imported_history=None):
    """Add newly fetched plays to the cumulative CSV and return all saved plays."""
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    if HISTORY_CSV.exists():
        history = _normalize_history_schema(pd.read_csv(HISTORY_CSV))
    else:
        history = pd.DataFrame(columns=HISTORY_COLUMNS)

    additions = []
    if imported_history is not None and not imported_history.empty:
        additions.append(imported_history.copy())
    if recently_played is not None and not recently_played.empty:
        additions.append(recently_played.copy())

    if additions:
        new_rows = _normalize_history_schema(pd.concat(additions, ignore_index=True))

        history = (
            new_rows.copy()
            if history.empty
            else pd.concat([history, new_rows], ignore_index=True)
        )
        event_keys = ["played_at_utc", "track_id"]
        for duration_column in ("track_duration_ms", "ms_played"):
            history[duration_column] = history.groupby(event_keys, dropna=False)[
                duration_column
            ].transform(lambda values: values.ffill().bfill())
        history = history.drop_duplicates(subset=event_keys, keep="last")
        history = history.sort_values("played_at_utc", ascending=False)

    history.to_csv(HISTORY_CSV, index=False)
    status(f"Updated {HISTORY_CSV} · {len(history):,} total plays")
    return history


def all_time_top_artists(history, limit=20):
    if history is None or history.empty:
        return pd.DataFrame()

    return (
        history.assign(artist=history["artist"].str.split(",").str[0].str.strip())
        .groupby("artist", as_index=False)
        .size()
        .sort_values("size", ascending=False)
        .head(limit)
        .rename(columns={"artist": "name", "size": "play_count"})
    )


def all_time_top_tracks(history, limit=20):
    if history is None or history.empty:
        return pd.DataFrame()

    return (
        history.groupby(["track_id", "name", "artist"], as_index=False)
        .size()
        .sort_values("size", ascending=False)
        .head(limit)
        .rename(columns={"size": "play_count"})
    )
