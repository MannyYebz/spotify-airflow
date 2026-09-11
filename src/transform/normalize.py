"""Explicit Arrow schemas and deterministic normalization of raw Spotify pages.

Malformed required fields fail the batch, leaving raw JSON available for repair.
Unavailable/local tracks have no stable Spotify ID and are counted and skipped.
"""

import hashlib
import logging

import pyarrow as pa

from src.extract.raw import DATASETS
from src.validation import (
    ValidationError,
    optional_int,
    optional_text,
    page_items,
    required_id,
    utc_timestamp,
)

log = logging.getLogger(__name__)
UTC = pa.timestamp("us", tz="UTC")
COMMON = [pa.field("extracted_at", UTC, nullable=False)]
TRACK = [
    pa.field("track_id", pa.string(), nullable=False),
    pa.field("name", pa.string()),
    pa.field("artist_ids", pa.list_(pa.string())),
    pa.field("artist_names", pa.list_(pa.string())),
    pa.field("album_id", pa.string()),
    pa.field("album", pa.string()),
    pa.field("track_duration_ms", pa.int64()),
]
SCHEMAS = {
    "recently_played": pa.schema(
        [
            pa.field("event_id", pa.string(), nullable=False),
            pa.field("played_at_utc", UTC, nullable=False),
            *TRACK,
            pa.field("ms_played", pa.int64()),
            *COMMON,
        ]
    ),
    "top_tracks": pa.schema(
        [
            pa.field("rank", pa.int32(), nullable=False),
            pa.field("time_range", pa.string(), nullable=False),
            *TRACK,
            *COMMON,
        ]
    ),
    "top_artists": pa.schema(
        [
            pa.field("rank", pa.int32(), nullable=False),
            pa.field("time_range", pa.string(), nullable=False),
            pa.field("artist_id", pa.string(), nullable=False),
            pa.field("name", pa.string()),
            pa.field("genres", pa.list_(pa.string())),
            *COMMON,
        ]
    ),
}


def track_fields(track: dict) -> dict:
    artists = track.get("artists")
    artists = [] if artists is None else artists
    album = track.get("album")
    album = {} if album is None else album
    if not isinstance(artists, list) or any(not isinstance(a, dict) for a in artists):
        raise ValidationError("Track artists must be an array of objects")
    if not isinstance(album, dict):
        raise ValidationError("Track album must be an object")
    return {
        "track_id": required_id(track.get("id"), "track_id"),
        "name": optional_text(track.get("name")),
        "artist_ids": [optional_text(a.get("id")) for a in artists],
        "artist_names": [optional_text(a.get("name")) for a in artists],
        "album_id": optional_text(album.get("id")),
        "album": optional_text(album.get("name")),
        "track_duration_ms": optional_int(track.get("duration_ms")),
    }


def normalize(raw: dict) -> pa.Table:
    if (
        not isinstance(raw, dict)
        or type(raw.get("schema_version")) is not int
        or raw["schema_version"] != 1
    ):
        raise ValidationError("Unsupported raw schema version")
    dataset = raw.get("dataset")
    if dataset not in DATASETS:
        raise ValidationError("Unknown raw dataset")
    extracted = utc_timestamp(raw.get("extracted_at"))
    start, end = (
        utc_timestamp(raw.get("interval_start")),
        utc_timestamp(raw.get("interval_end")),
    )
    if start >= end:
        raise ValidationError("Invalid raw interval")
    pages = raw.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ValidationError("Raw pages must be a nonempty array")
    items = [item for page in pages for item in page_items(page)]
    if dataset != "recently_played":
        if raw.get("time_range") not in {"short_term", "medium_term", "long_term"}:
            raise ValidationError("Invalid raw time_range")
        limit = raw.get("top_limit")
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValidationError("Invalid raw top_limit")
        items = items[:limit]
    rows, seen, skipped = [], set(), 0
    for rank, item in enumerate(items, 1):
        row = {"extracted_at": extracted}
        if dataset == "top_artists":
            identity = required_id(item.get("id"), "artist_id")
            genres = item.get("genres")
            genres = [] if genres is None else genres
            if not isinstance(genres, list) or any(
                not isinstance(g, str) for g in genres
            ):
                raise ValidationError("Artist genres must be an array of strings")
            row.update(
                artist_id=identity,
                name=optional_text(item.get("name")),
                genres=list(dict.fromkeys(g.strip() for g in genres if g.strip())),
            )
        else:
            track = item.get("track") if dataset == "recently_played" else item
            if track is None:
                skipped += 1
                continue
            if not isinstance(track, dict):
                raise ValidationError("Track must be an object or null")
            if track.get("is_local") is True or track.get("id") is None:
                skipped += 1
                continue
            row.update(track_fields(track))
            identity = row["track_id"]
            if dataset == "recently_played":
                played = utc_timestamp(item.get("played_at"))
                if not start <= played < end:
                    continue
                identity = hashlib.sha256(
                    f"{identity}|{played.isoformat()}".encode()
                ).hexdigest()
                row.update(event_id=identity, played_at_utc=played, ms_played=None)
        if dataset != "recently_played":
            row.update(rank=rank, time_range=raw["time_range"])
        if identity not in seen:
            rows.append(row)
            seen.add(identity)
    if dataset == "recently_played":
        rows.sort(key=lambda row: (row["played_at_utc"], row["track_id"]))
    table = pa.Table.from_pylist(rows, schema=SCHEMAS[dataset])
    table.validate(full=True)
    log.info(
        "Normalized dataset=%s input=%s output=%s unavailable=%s",
        dataset,
        len(items),
        len(rows),
        skipped,
    )
    return table
