"""DataFrame adapters retained for the original local reports."""

from datetime import datetime, timezone

from src.config import Settings
from src.extract.raw import extract_dataset
from src.spotify import BASE_URL, SpotifyClient
from src.transform.normalize import normalize

RECENTLY_PLAYED_COLUMNS = [
    "played_at_utc",
    "name",
    "artist",
    "album",
    "track_duration_ms",
    "ms_played",
    "track_id",
]


def get_user_profile():
    return SpotifyClient(Settings.from_env()).get(BASE_URL + "/me")


def _frame(dataset, time_range, limit):
    from dataclasses import replace

    settings = replace(Settings.from_env(), time_range=time_range, top_limit=limit)
    settings.validate()
    now = datetime.now(timezone.utc)
    client = SpotifyClient(settings)
    start = datetime(1970, 1, 1, tzinfo=timezone.utc).isoformat()
    if dataset == "recently_played":
        # A report asks for the latest available plays, not an ETL interval.
        raw = {
            "schema_version": 1,
            "dataset": dataset,
            "interval_start": start,
            "interval_end": now.isoformat(),
            "extracted_at": now.isoformat(),
            "pages": client.pages(
                "/me/player/recently-played", {"limit": min(50, limit)}, max_items=limit
            ),
        }
    else:
        raw = extract_dataset(client, dataset, start, now.isoformat())
    frame = normalize(raw).to_pandas()
    if "artist_names" in frame:
        frame["artist"] = frame["artist_names"].map(
            lambda names: ", ".join(n or "Unknown" for n in names)
        )
    if "genres" in frame:
        frame["genres"] = frame["genres"].map(lambda genres: ", ".join(genres) or "N/A")
    if dataset == "recently_played":
        frame = frame.sort_values("played_at_utc", ascending=False)
    return frame.head(limit)


def get_top_artists(time_range="medium_term", limit=20):
    return _frame("top_artists", time_range, limit)


def get_top_tracks(time_range="medium_term", limit=20):
    return _frame("top_tracks", time_range, limit)


def get_recently_played(limit=50):
    frame = _frame("recently_played", "medium_term", limit)
    frame["played_at_utc"] = frame["played_at_utc"].map(lambda value: value.isoformat())
    return frame[RECENTLY_PLAYED_COLUMNS]
