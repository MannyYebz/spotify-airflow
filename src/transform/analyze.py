"""Editorial chart generation for the Spotify listening archive.

The figures borrow their visual language from an independent music journal:
paper, ink, typographic hierarchy, measured rules, and deliberately different
compositions for rankings, time distributions, and counted data.
"""

from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

from src.utils.terminal import status

LOCAL_TZ = "America/New_York"
DPI = 200
PAGE_WIDTH = 11.5
LEFT = 0.72
RIGHT = PAGE_WIDTH - 0.72

# Paper and ink, with oxblood reserved for the single finding that matters most.
PAPER = "#F3EFE5"
INK = "#181714"
SECONDARY = "#68635B"
QUIET = "#999187"
RULE = "#BDB5A8"
OXBLOOD = "#762E2A"

SERIF = ["Gelasio", "DejaVu Serif"]
SANS = ["Inter", "Arimo", "DejaVu Sans"]
MONO = ["JetBrains Mono", "Cousine", "DejaVu Sans Mono"]

_GENERATED_CHARTS = []

plt.rcParams.update(
    {
        "figure.facecolor": PAPER,
        "savefig.facecolor": PAPER,
        "axes.facecolor": PAPER,
        "axes.edgecolor": RULE,
        "axes.labelcolor": SECONDARY,
        "xtick.color": SECONDARY,
        "ytick.color": SECONDARY,
        "text.color": INK,
        "font.family": "sans-serif",
        "font.sans-serif": SANS,
        "font.size": 10,
        "figure.dpi": DPI,
        "savefig.dpi": DPI,
    }
)


def _format_hour(hour):
    if hour == 0:
        return "12 AM"
    if hour < 12:
        return f"{hour} AM"
    if hour == 12:
        return "12 PM"
    return f"{hour - 12} PM"


def _truncate(text, limit):
    text = str(text)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _is_archive(output_path):
    return "all_time" in Path(output_path).stem


def _new_page(height):
    return plt.figure(figsize=(PAGE_WIDTH, height), facecolor=PAPER)


def _folio(fig, output_path, figure_number):
    """Add the quiet recurring furniture of a printed publication."""
    height = fig.get_figheight()
    top = 1 - 0.38 / height
    bottom_rule = 0.48 / height
    bottom_text = 0.25 / height
    archive = _is_archive(output_path)
    collection = (
        "LISTENING ARCHIVE · COMPLETE RECORD"
        if archive
        else "LISTENING ARCHIVE · RECENT EDITION"
    )
    source = "Spotify export + Web API" if archive else "Spotify Web API"

    fig.text(
        LEFT / PAGE_WIDTH,
        top,
        collection,
        fontsize=7.2,
        color=SECONDARY,
        fontfamily=SANS,
    )
    fig.text(
        RIGHT / PAGE_WIDTH,
        top,
        datetime.now().strftime("%d %b %Y").upper(),
        ha="right",
        fontsize=7.2,
        color=SECONDARY,
        fontfamily=MONO,
    )
    fig.add_artist(
        Line2D(
            [LEFT / PAGE_WIDTH, RIGHT / PAGE_WIDTH],
            [bottom_rule, bottom_rule],
            transform=fig.transFigure,
            color=RULE,
            linewidth=0.55,
        )
    )
    fig.text(
        LEFT / PAGE_WIDTH,
        bottom_text,
        f"FIG. {figure_number:02d}  ·  {source}",
        fontsize=7,
        color=QUIET,
    )
    fig.text(
        RIGHT / PAGE_WIDTH,
        bottom_text,
        f"{figure_number:02d}",
        ha="right",
        fontsize=7,
        color=QUIET,
        fontfamily=MONO,
    )


def _title(fig, title, observation, *, y=0.875, x=None):
    """Set an editorial title and observation without imposing a chart grid."""
    x = LEFT / PAGE_WIDTH if x is None else x
    fig.text(
        x,
        y,
        title,
        fontsize=27,
        color=INK,
        fontfamily=SERIF,
        fontweight="normal",
        va="top",
    )
    fig.text(
        x,
        y - 0.075,
        observation,
        fontsize=9.5,
        color=SECONDARY,
        fontfamily=SANS,
        va="top",
        wrap=True,
    )


def _save(fig, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, facecolor=PAPER)
    _GENERATED_CHARTS.append(output_path)
    plt.close(fig)
    status(f"Saved {output_path}")


def show_charts():
    """Display generated charts sequentially, advancing when each is closed."""
    if not _GENERATED_CHARTS:
        status("No charts to display")
        return

    chart_count = len(_GENERATED_CHARTS)
    status("Opening charts one at a time · close each chart to continue")
    try:
        for position, chart_path in enumerate(_GENERATED_CHARTS, start=1):
            image = plt.imread(chart_path)
            height, width = image.shape[:2]
            fig, ax = plt.subplots(figsize=(width / DPI, height / DPI), dpi=DPI)
            fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
            ax.imshow(image)
            ax.axis("off")
            manager = getattr(fig.canvas, "manager", None)
            if manager and hasattr(manager, "set_window_title"):
                manager.set_window_title(
                    f"{position} of {chart_count} · {chart_path.stem.replace('_', ' ').title()}"
                )
            plt.show(block=True)
            plt.close(fig)
    finally:
        _GENERATED_CHARTS.clear()


def _ranked_artist_page(output_path, title, labels, genres=None, counts=None):
    """A two-column record-catalogue ranking led by large rank numerals."""
    labels = list(labels)[:10]
    genres = list(genres)[:10] if genres is not None else [""] * len(labels)
    counts = list(counts)[:10] if counts is not None else None
    fig = _new_page(8.4)
    observation = (
        f"{labels[0]} leads the record with {int(counts[0]):,} documented plays."
        if counts is not None
        else f"{labels[0]} occupies the first position in Spotify’s four-week ranking."
    )
    _folio(fig, output_path, 1)
    _title(fig, title, observation, y=0.885)

    top, row_gap = 0.69, 0.108
    column_x = [LEFT / PAGE_WIDTH, 0.535]
    for index, label in enumerate(labels):
        column, row = divmod(index, 5)
        x = column_x[column]
        y = top - row * row_gap
        rank_color = OXBLOOD if index == 0 else QUIET
        fig.text(
            x,
            y,
            f"{index + 1:02d}",
            fontsize=25,
            color=rank_color,
            fontfamily=MONO,
            va="top",
        )
        fig.text(
            x + 0.078,
            y - 0.002,
            _truncate(label, 28),
            fontsize=15.5,
            color=INK,
            fontfamily=SERIF,
            va="top",
        )
        detail = _truncate(genres[index], 34) if genres[index] else "Artist"
        if counts is not None:
            detail = f"{int(counts[index]):,} plays" + (
                f"  ·  {detail}" if genres[index] else ""
            )
        fig.text(x + 0.078, y - 0.039, detail, fontsize=8.2, color=SECONDARY, va="top")
        x_end = 0.47 if column == 0 else RIGHT / PAGE_WIDTH
        fig.add_artist(
            Line2D(
                [x + 0.078, x_end],
                [y - 0.066, y - 0.066],
                transform=fig.transFigure,
                color=RULE,
                linewidth=0.45,
            )
        )

    _save(fig, output_path)


def _ranked_track_page(output_path, title, names, artists, albums=None, counts=None):
    """A single-column track index with titles dominant over discographic data."""
    names, artists = list(names)[:10], list(artists)[:10]
    albums = list(albums)[:10] if albums is not None else [""] * len(names)
    counts = list(counts)[:10] if counts is not None else None
    fig = _new_page(10.1)
    observation = (
        f"{names[0]} by {artists[0]} is the most frequently documented track ({int(counts[0]):,} plays)."
        if counts is not None
        else f"{names[0]} by {artists[0]} opens the current four-week ranking."
    )
    _folio(fig, output_path, 2)
    _title(fig, title, observation, y=0.9)

    top, row_gap = 0.735, 0.067
    for index, (name, artist, album) in enumerate(zip(names, artists, albums)):
        y = top - index * row_gap
        fig.text(
            LEFT / PAGE_WIDTH,
            y,
            f"{index + 1:02d}",
            fontsize=13.5,
            color=OXBLOOD if index == 0 else QUIET,
            fontfamily=MONO,
            va="top",
        )
        fig.text(
            0.135,
            y + 0.002,
            _truncate(name, 54),
            fontsize=13.5,
            color=INK,
            fontfamily=SERIF,
            va="top",
        )
        metadata = _truncate(artist, 34)
        if album and str(album) not in ("nan", "N/A"):
            metadata += f"  /  {_truncate(album, 46)}"
        fig.text(0.135, y - 0.026, metadata, fontsize=8.2, color=SECONDARY, va="top")
        if counts is not None:
            fig.text(
                RIGHT / PAGE_WIDTH,
                y,
                f"{int(counts[index]):,}",
                ha="right",
                fontsize=9,
                color=INK,
                fontfamily=MONO,
                va="top",
            )
            fig.text(
                RIGHT / PAGE_WIDTH,
                y - 0.025,
                "plays",
                ha="right",
                fontsize=7.2,
                color=QUIET,
                va="top",
            )
        fig.add_artist(
            Line2D(
                [0.135, RIGHT / PAGE_WIDTH],
                [y - 0.047, y - 0.047],
                transform=fig.transFigure,
                color=RULE,
                linewidth=0.42,
            )
        )

    _save(fig, output_path)


def plot_top_artists(df, output_path="charts/top_artists.png", title="Top artists"):
    if df is None or df.empty:
        print("  Top artists: no data yet.")
        return
    top = df.head(10)
    genres = (
        top["genres"].fillna("").astype(str).tolist()
        if "genres" in top.columns
        else None
    )
    counts = top["play_count"].tolist() if "play_count" in top.columns else None
    _ranked_artist_page(output_path, title, top["name"].astype(str), genres, counts)


def plot_top_tracks(df, output_path="charts/top_tracks.png", title="Top tracks"):
    if df is None or df.empty:
        print("  Top tracks: no data yet.")
        return
    top = df.head(10)
    albums = (
        top["album"].fillna("").astype(str).tolist() if "album" in top.columns else None
    )
    counts = top["play_count"].tolist() if "play_count" in top.columns else None
    _ranked_track_page(
        output_path,
        title,
        top["name"].astype(str),
        top["artist"].astype(str),
        albums,
        counts,
    )


def _local_hours(df):
    timestamp_column = "played_at_utc" if "played_at_utc" in df.columns else "played_at"
    timestamps = pd.to_datetime(
        df[timestamp_column], format="mixed", utc=True, errors="coerce"
    )
    return timestamps.dt.tz_convert(LOCAL_TZ).dt.hour


def plot_listening_hours(
    df, output_path="charts/listening_hours.png", title="Listening by hour"
):
    if df is None or df.empty:
        print("  Listening hours: no data yet.")
        return
    hours = _local_hours(df)
    if hours.isna().all():
        print("  Listening hours: no valid timestamps found.")
        return

    counts = hours.value_counts().reindex(range(24), fill_value=0)
    peak_hour, peak_count = int(counts.idxmax()), int(counts.max())
    fig = _new_page(7.0)
    _folio(fig, output_path, 3)
    _title(
        fig,
        title,
        f"Listening activity across {int(counts.sum()):,} recorded plays.",
        y=0.865,
    )

    # The finding sits apart from the figure, like a pull statistic in a feature.
    fig.text(
        0.78,
        0.855,
        _format_hour(peak_hour),
        fontsize=29,
        color=OXBLOOD,
        fontfamily=SERIF,
        ha="left",
        va="top",
    )
    fig.text(
        0.78,
        0.79,
        "peak listening hour",
        fontsize=8.5,
        color=SECONDARY,
        ha="left",
        va="top",
    )

    ax = fig.add_axes([LEFT / PAGE_WIDTH, 0.19, 0.87, 0.46])
    x = np.arange(24)
    ax.vlines(x, 0, counts.values, color=RULE, linewidth=0.8, zorder=1)
    ax.plot(x, counts.values, color=INK, linewidth=0.85, zorder=2)
    ax.scatter(
        x, counts.values, s=10, color=PAPER, edgecolor=INK, linewidth=0.7, zorder=3
    )
    ax.vlines(peak_hour, 0, peak_count, color=OXBLOOD, linewidth=1.4, zorder=4)
    ax.scatter(
        [peak_hour],
        [peak_count],
        s=29,
        color=OXBLOOD,
        edgecolor=PAPER,
        linewidth=0.8,
        zorder=5,
    )
    ax.annotate(
        f"{peak_count:,} plays",
        (peak_hour, peak_count),
        xytext=(0, 13),
        textcoords="offset points",
        ha="center",
        fontsize=8.2,
        color=OXBLOOD,
        fontfamily=MONO,
    )

    ax.set_xlim(-0.5, 23.5)
    ax.set_ylim(0, max(peak_count * 1.18, 1))
    ax.set_xticks(range(0, 24, 3), [_format_hour(hour) for hour in range(0, 24, 3)])
    ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True, nbins=4))
    ax.tick_params(axis="both", length=0, pad=8, labelsize=7.8)
    for label in [*ax.get_xticklabels(), *ax.get_yticklabels()]:
        label.set_fontfamily(MONO)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.spines["bottom"].set_color(INK)
    ax.spines["bottom"].set_linewidth(0.65)
    ax.grid(axis="y", color=RULE, linewidth=0.4)
    ax.set_axisbelow(True)
    ax.text(
        -0.055,
        1.0,
        "PLAYS",
        transform=ax.transAxes,
        fontsize=7,
        color=QUIET,
        va="bottom",
    )
    _save(fig, output_path)


def plot_time_of_day(
    df, output_path="charts/time_of_day.png", title="Listening by time of day"
):
    if df is None or df.empty:
        print("  Time of day: no data yet.")
        return
    hours = _local_hours(df)
    valid = hours.notna()
    if not valid.any():
        print("  Time of day: no valid timestamps found.")
        return
    if "ms_played" not in df.columns:
        _plot_unavailable_listening_duration(output_path, title)
        return
    durations = pd.to_numeric(df.loc[valid, "ms_played"], errors="coerce")
    measured = durations.notna()
    if not measured.any():
        _plot_unavailable_listening_duration(output_path, title)
        return

    hours = hours[valid][measured]
    durations = durations[measured] / 60000
    periods = pd.cut(
        hours,
        bins=[-1, 5, 11, 17, 21, 23],
        labels=["Late night", "Morning", "Afternoon", "Evening", "Night"],
    )
    order = ["Morning", "Afternoon", "Evening", "Night", "Late night"]
    windows = ["6–12", "12–18", "18–22", "22–24", "0–6"]
    minutes = (
        durations.groupby(periods, observed=False).sum().reindex(order, fill_value=0)
    )
    total = float(minutes.sum())
    percentages = minutes.to_numpy() / total * 100 if total else np.zeros(len(minutes))
    peak = int(np.argmax(percentages))

    fig = _new_page(7.2)
    _folio(fig, output_path, 4)
    _title(
        fig,
        title,
        f"Distribution of {total / 60:,.1f} measured listening hours.",
        y=0.87,
    )
    fig.text(
        LEFT / PAGE_WIDTH,
        0.68,
        f"{percentages[peak]:.0f}%",
        fontsize=43,
        color=OXBLOOD,
        fontfamily=SERIF,
        va="top",
    )
    fig.text(
        0.22,
        0.665,
        f"of measured listening\noccurs in the {order[peak].lower()}",
        fontsize=13,
        color=INK,
        fontfamily=SERIF,
        linespacing=1.35,
        va="top",
    )

    ax = fig.add_axes([LEFT / PAGE_WIDTH, 0.28, 0.87, 0.16])
    starts = np.r_[0, np.cumsum(percentages)[:-1]]
    for index, (start, width) in enumerate(zip(starts, percentages)):
        color = OXBLOOD if index == peak else (INK if index % 2 == 0 else SECONDARY)
        ax.barh(
            0,
            width,
            left=start,
            height=0.22,
            color=color,
            edgecolor=PAPER,
            linewidth=1.3,
        )
    ax.set_xlim(0, 100)
    ax.set_ylim(-0.7, 0.7)
    ax.axis("off")

    for index, (name, percentage) in enumerate(zip(order, percentages)):
        x = LEFT / PAGE_WIDTH + index * 0.174
        fig.text(x, 0.23, name, fontsize=8.5, color=INK, va="top")
        fig.text(
            x,
            0.195,
            f"{percentage:.1f}%",
            fontsize=9,
            color=OXBLOOD if index == peak else SECONDARY,
            fontfamily=MONO,
            va="top",
        )
        fig.text(
            x, 0.166, windows[index], fontsize=7, color=QUIET, fontfamily=MONO, va="top"
        )
    _save(fig, output_path)


def _plot_unavailable_listening_duration(output_path, title):
    fig = _new_page(6.2)
    _folio(fig, output_path, 4)
    _title(fig, title, "A necessary absence in the recent record.", y=0.85)
    fig.text(
        LEFT / PAGE_WIDTH,
        0.55,
        "—",
        fontsize=50,
        color=OXBLOOD,
        fontfamily=SERIF,
        va="top",
    )
    fig.text(
        0.2,
        0.55,
        "Listening-time data unavailable",
        fontsize=20,
        color=INK,
        fontfamily=SERIF,
        va="top",
    )
    fig.text(
        0.2,
        0.47,
        "Spotify’s recently played API records when a track began,\nbut not how long it was heard.",
        fontsize=10,
        color=SECONDARY,
        linespacing=1.55,
        va="top",
    )
    _save(fig, output_path)


def plot_most_played_artists(
    df, output_path="charts/most_played_artists.png", title="Most-played artists"
):
    if df is None or df.empty:
        print("  Most played artists: no data yet.")
        return
    counts = df["artist"].str.split(",").str[0].str.strip().value_counts().head(8)
    values = counts.to_numpy(dtype=float)
    maximum = float(values.max())
    leaders = counts[counts == maximum].index.tolist()
    if len(leaders) == 1:
        observation = (
            f"{leaders[0]} appears most often, with {int(maximum):,} recorded plays."
        )
    elif len(leaders) == 2:
        observation = f"{leaders[0]} and {leaders[1]} share the lead at {int(maximum):,} recorded plays each."
    else:
        observation = f"{len(leaders)} artists share the lead at {int(maximum):,} recorded plays each."

    fig = _new_page(7.9)
    _folio(fig, output_path, 5)
    _title(fig, title, observation, y=0.875)
    ax = fig.add_axes([0.36, 0.15, 0.57, 0.57])
    y = np.arange(len(counts))
    ax.barh(
        y,
        values,
        height=0.16,
        color=[OXBLOOD if value == maximum else INK for value in values],
        edgecolor="none",
    )
    ax.set_xlim(0, max(maximum * 1.16, 1))
    ax.set_ylim(len(counts) - 0.5, -0.5)
    ax.set_yticks([])
    ax.xaxis.set_major_locator(plt.MaxNLocator(integer=True, nbins=5))
    ax.tick_params(axis="x", length=3, width=0.5, color=RULE, labelsize=7.5, pad=7)
    for label in ax.get_xticklabels():
        label.set_fontfamily(MONO)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.spines["bottom"].set_color(RULE)
    ax.spines["bottom"].set_linewidth(0.5)
    ax.grid(False)

    for index, (artist, value) in enumerate(zip(counts.index, values)):
        color = OXBLOOD if value == maximum else QUIET
        ax.text(
            -0.55 * maximum,
            index,
            f"{index + 1:02d}",
            ha="left",
            va="center",
            fontsize=9,
            color=color,
            fontfamily=MONO,
            clip_on=False,
        )
        ax.text(
            -0.43 * maximum,
            index,
            _truncate(artist, 25),
            ha="left",
            va="center",
            fontsize=11.5,
            color=INK,
            fontfamily=SERIF,
            clip_on=False,
        )
        ax.text(
            value + maximum * 0.018,
            index,
            f"{int(value):,}",
            ha="left",
            va="center",
            fontsize=8.3,
            color=INK,
            fontfamily=MONO,
        )
    ax.text(0, -0.8, "DOCUMENTED PLAYS", fontsize=7, color=QUIET, va="bottom")
    _save(fig, output_path)
