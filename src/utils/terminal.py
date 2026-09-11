"""Quiet, consistent terminal presentation for the listening report."""

import pandas as pd

LOCAL_TZ = "America/New_York"
RULE_WIDTH = 78


def title(text, eyebrow="SPOTIFY LISTENING ARCHIVE"):
    print(f"\n  {eyebrow.upper()}")
    print(f"  {text}")
    print(f"  {'─' * RULE_WIDTH}")


def status(message):
    print(f"  · {message}")


def _table(rows, columns):
    headings = "  ".join(f"{label:<{width}}" for _, label, width in columns)
    print(f"  {headings}")
    print(f"  {'─' * len(headings)}")
    for _, row in rows.iterrows():
        values = "  ".join(
            f"{str(row.get(key, ''))[:width]:<{width}}" for key, _, width in columns
        )
        print(f"  {values}")


def profile(data):
    title("Listener profile", "ACCOUNT")
    print(f"  {'Name':<16}{data.get('display_name', 'Unknown')}")
    print(f"  {'Plan':<16}{data.get('product', 'unknown').title()}")
    print(f"  {'Followers':<16}{data.get('followers', {}).get('total', 0):,}")


def ranked_artists(data, time_range="medium_term"):
    label = time_range.replace("_", " ").title()
    title("Artists in rotation", label)
    if data.empty:
        status("No ranking is available yet.")
        return
    _table(data, [("rank", "NO.", 4), ("name", "ARTIST", 27), ("genres", "GENRES", 39)])


def ranked_tracks(data, time_range="medium_term"):
    label = time_range.replace("_", " ").title()
    title("Tracks in rotation", label)
    if data.empty:
        status("No ranking is available yet.")
        return
    _table(
        data,
        [
            ("rank", "NO.", 4),
            ("name", "TRACK", 29),
            ("artist", "ARTIST", 23),
            ("album", "ALBUM", 22),
        ],
    )


def listening_history(data, heading, limit=10):
    count = 0 if data is None else len(data)
    title(heading, f"{count:,} PLAYS")
    if data is None or data.empty:
        status("No listening history is available.")
        return

    display = data.copy()
    timestamps = pd.to_datetime(display["played_at_utc"], utc=True, errors="coerce")
    display["played_at_local"] = timestamps.dt.tz_convert(LOCAL_TZ).dt.strftime(
        "%b %d  %I:%M %p"
    )
    display = (
        display.assign(_timestamp=timestamps)
        .sort_values("_timestamp", ascending=False, na_position="last")
        .head(limit)
    )
    _table(
        display,
        [
            ("played_at_local", "PLAYED AT", 18),
            ("name", "TRACK", 33),
            ("artist", "ARTIST", 25),
        ],
    )


def dashboard(profile_data, top_artists, top_tracks, recently_played, time_range):
    profile(profile_data)
    ranked_artists(top_artists, time_range)
    ranked_tracks(top_tracks, time_range)
    listening_history(recently_played, "Recently played")
