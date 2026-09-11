from dotenv import load_dotenv

from src.extract.fetch_data import (
    get_recently_played,
    get_top_artists,
    get_top_tracks,
    get_user_profile,
)
from src.transform.analytics_history import (
    HISTORY_DIR,
    RECENT_HISTORY_DIR,
    all_time_top_artists,
    all_time_top_tracks,
    import_extended_streaming_history,
    save_recent_listening_history,
    update_listening_history,
)
from src.transform.analyze import (
    plot_listening_hours,
    plot_most_played_artists,
    plot_time_of_day,
    plot_top_artists,
    plot_top_tracks,
    show_charts,
)
from src.utils.terminal import dashboard, status, title
from src.utils.terminal import listening_history as print_listening_history

EXTENDED_HISTORY_DIR = "data/Spotify Extended Streaming History"


def main():
    load_dotenv()
    title("A portrait of recent and archival listening")

    # Step 1: Fetch all data
    profile = get_user_profile()
    top_artists = get_top_artists("short_term", 20)
    top_tracks = get_top_tracks("short_term", 20)
    recently_played = get_recently_played(50)

    dashboard(profile, top_artists, top_tracks, recently_played, "short_term")

    # Refresh the latest snapshot and keep the cumulative all-time history.
    save_recent_listening_history(recently_played)
    imported_history = import_extended_streaming_history(EXTENDED_HISTORY_DIR)

    # Add only new plays to the cumulative history used by all-time charts.
    listening_history = update_listening_history(recently_played, imported_history)

    # Step 2: Generate charts
    title("Preparing the visual report", "ANALYSIS")

    # Keep the newest charts together with the recent-listening CSV.
    plot_top_artists(top_artists, RECENT_HISTORY_DIR / "top_artists.png")
    plot_top_tracks(top_tracks, RECENT_HISTORY_DIR / "top_tracks.png")
    plot_listening_hours(recently_played, RECENT_HISTORY_DIR / "listening_hours.png")
    plot_time_of_day(recently_played, RECENT_HISTORY_DIR / "time_of_day.png")
    plot_most_played_artists(
        recently_played, RECENT_HISTORY_DIR / "most_played_artists.png"
    )

    # Generate the archived charts from every play collected so far.
    plot_top_artists(
        all_time_top_artists(listening_history),
        HISTORY_DIR / "all_time_top_artists.png",
        "All-time top artists",
    )
    plot_top_tracks(
        all_time_top_tracks(listening_history),
        HISTORY_DIR / "all_time_top_tracks.png",
        "All-time top tracks",
    )
    plot_listening_hours(
        listening_history,
        HISTORY_DIR / "all_time_listening_hours.png",
        "All-time listening by hour",
    )
    plot_time_of_day(
        listening_history,
        HISTORY_DIR / "all_time_time_of_day.png",
        "All-time listening by time of day",
    )
    plot_most_played_artists(
        listening_history,
        HISTORY_DIR / "all_time_most_played_artists.png",
        "All-time most-played artists",
    )

    # Show both datasets in order immediately before the program exits.
    print_listening_history(recently_played, "Current listening history")
    print_listening_history(listening_history, "Cumulative listening history")

    status("Report complete · recent_history and analytics_history are up to date")
    show_charts()


if __name__ == "__main__":
    main()
