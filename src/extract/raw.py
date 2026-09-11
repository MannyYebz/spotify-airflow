"""Extract complete API pages without discarding the source response."""

from datetime import datetime, timezone

from src.spotify import SpotifyClient
from src.validation import ValidationError, utc_timestamp

DATASETS = ("recently_played", "top_tracks", "top_artists")


def extract_dataset(client: SpotifyClient, dataset: str, start: str, end: str) -> dict:
    start_dt, end_dt = utc_timestamp(start), utc_timestamp(end)
    if start_dt >= end_dt:
        raise ValidationError("Interval start must be before end")
    if dataset == "recently_played":
        pages = client.pages(
            "/me/player/recently-played",
            {
                "limit": 50,
                "after": int(start_dt.timestamp() * 1000) - 1,
            },
        )
    elif dataset in {"top_tracks", "top_artists"}:
        pages = client.pages(
            "/me/top/" + dataset.removeprefix("top_"),
            {
                "limit": min(50, client.settings.top_limit),
                "time_range": client.settings.time_range,
                "offset": 0,
            },
            max_items=client.settings.top_limit,
        )
    else:
        raise ValidationError("Unknown dataset")
    return {
        "schema_version": 1,
        "dataset": dataset,
        "interval_start": start_dt.isoformat(),
        "interval_end": end_dt.isoformat(),
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "time_range": client.settings.time_range
        if dataset != "recently_played"
        else None,
        "top_limit": client.settings.top_limit,
        "pages": pages,
    }
