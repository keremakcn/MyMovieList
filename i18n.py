"""UI-only localization. Catalog data and persisted movie values stay canonical."""

import ctypes
import json
import locale
import os
import sys
from pathlib import Path

from flask import g, has_request_context

SUPPORTED_LANGUAGES = ("en", "tr")
TRANSLATIONS = json.loads(
    (Path(__file__).resolve().parent / "static" / "locales" / "tr.json").read_text(
        encoding="utf-8"
    )
)

CLIENT_MESSAGES = frozenset(
    (
        "Add to favorites",
        "Add {title} to showcase",
        "Remove {title} from showcase",
        "Move {title} earlier",
        "Move {title} later",
        "Film not available on this device",
        "Removed or not yet synced. You can remove this pick.",
        "Page {page} of {pages}",
        "Six films selected. Remove one to choose another.",
        "Added as watched.",
        "Added to Want to Watch.",
        "Adding…",
        "All films on this page are in your library. Try the next page.",
        "Could not complete the request. Please try again.",
        "Could not load these films. Check your connection and try again.",
        "Could not load these films. Please try again.",
        "Could not refresh your library. Please try again.",
        "Dismiss notification",
        "Edit {title} — {status}",
        "I liked {title}",
        "Image unavailable",
        "Poster for {title}",
        "Remove {title}",
        "View note for {title}",
        "In your library",
        "Library updated.",
        "Loading films…",
        "Loading suggestions…",
        "Mark watched",
        "Movie",
        "Movie removed.",
        "Movie removed. Use Undo below or restore it from Recently removed.",
        "Movie restored — notes, rating and original order preserved.",
        "New suggestions",
        "Next results",
        "No films found. Try another title.",
        "No suggestions. Press Enter to search.",
        "Press Search to apply your filters.",
        "Recently removed",
        "Refreshing…",
        "Remove from favorites",
        "Remove {title} from your picks",
        "Saving your picks. Please keep this page open…",
        "Select at least one category.",
        "Select films you have seen and enjoyed. Your picks stay selected as you browse.",
        "Show different films",
        "Something went wrong. Please try again.",
        "Suggestion hidden. Other films in this genre are unaffected.",
        "Try again",
        "Undo",
        "Want to watch",
        "Watched",
        "Watched {date}",
        "Year unknown",
        "You can select up to 24 films.",
        "{count} film on this page",
        "{count} films on this page",
        "{count} suggestions available. Use the arrow keys.",
        "{error} Your selections are still here. Please try again.",
        "✓ Already in your library — Click to edit",
        "✓ In your library",
        "✓ In your library.",
        "New version available: {version}",
        "Download update",
        "Dismiss update notice",
        "No rating yet",
        "Rating saved.",
        "Rating cleared.",
        "Action",
        "Adventure",
        "Animation",
        "Comedy",
        "Crime",
        "Documentary",
        "Drama",
        "Family",
        "Fantasy",
        "History",
        "Horror",
        "Music",
        "Mystery",
        "Romance",
        "Science Fiction",
        "TV Movie",
        "Thriller",
        "War",
        "Western",
        "Favorites",
        "Average rating",
        "Watch time",
        "{count} in library",
        "{hours}h {minutes}m",
        "{days} days · {count} films",
        "{minutes} min across {count} films",
        "{count} rated · median {median}",
        "{count} rated",
        "No ratings yet",
        "{count} want to watch",
        "Drawn to {genre}",
        "Your personal archive is taking shape",
        "A film lover",
        "Peak era: {era}",
        "+{delta} above TMDB avg",
        "{delta} below TMDB avg",
        "Matches TMDB avg ({avg})",
        "Best streak: {days} days",
        "{count} masterpieces (10/10)",
        "Avg runtime: {min} min",
        "Watched in {year}: {count}",
        "MYMOVIELIST · CINEMA PASSPORT · {year}",
        "My Cinema Profile.",
        "RATING DISTRIBUTION (1–10)",
        "★ {avg} average · {count} rated",
        "TOP GENRES",
        "{count} film",
        "{count} films",
        "MOST WATCHED DIRECTOR",
        "{count} watched",
        "HIGHEST RATED PICKS",
        "ARCHIVE MILESTONE",
        "Longest watched",
        "Oldest film",
        "min",
        "Genres will appear as you add films.",
        "Rate watched films to highlight your top picks.",
        "Private notes stay private",
        "PRIVATE SCREENING PASSPORT",
        "Cinema card downloaded.",
        "Cinema card copied to clipboard.",
        "Could not copy image. Use Download PNG instead.",
        "Copied",
        "Copy image",
        "Download PNG",
        "Quick actions",
        "3D Spatial Shelf view",
        "View your collection as physical 3D spines",
        "Cinematic Poster Grid",
        "Portrait posters with dynamic glare & note badges",
        "Critic's Editorial List",
        "Filmstrip dossier with director, date & journal",
        "Switch interface language",
        "Instant bilingual interface switch",
        "Navigate",
        "Library",
        "Your personal collection",
        "Explore",
        "Trending, top rated & genre portals",
        "For you",
        "3-mode personal discovery frequency dial",
        "Cinema stats",
        "Constellation radar, heatmap & auteur podium",
        "Social",
        "Public showcases & watched this week",
        "Favorite people",
        "Private actors & directors collection",
        "Import from Letterboxd or IMDb",
        "Bring .zip or .csv history into your vault",
        "Your library",
        "Catalog · Movies, Filmmakers & Studios",
        "Open",
        "Auto-saving…",
        "Auto-saved ✓",
        "Unsaved draft…",
        "Not saved yet — press Save changes.",
        "Hover or click an active day to inspect films",
        "No films recorded for this selection.",
    )
)


def normalize_language(value):
    """Only a Turkish OS language selects Turkish; every other OS uses English."""
    primary = str(value or "").lower().replace("_", "-").split("-")[0]
    return "tr" if primary in ("tr", "turkish") else "en"


def detect_system_language(android=False):
    if android:
        try:
            from java import jclass

            return normalize_language(
                jclass("java.util.Locale").getDefault().getLanguage()
            )
        except (ImportError, AttributeError, RuntimeError):
            return "en"
    if sys.platform == "win32":
        try:
            getter = ctypes.WinDLL(
                "kernel32", use_last_error=True
            ).GetUserDefaultUILanguage
            getter.restype = ctypes.c_ushort
            getter.argtypes = []
            return "tr" if getter() & 0x3FF == 0x1F else "en"
        except (AttributeError, OSError):
            pass
    elif sys.platform == "darwin":
        try:
            from Foundation import NSLocale

            languages = NSLocale.preferredLanguages()
            if languages:
                return normalize_language(str(languages[0]))
        except (ImportError, AttributeError, RuntimeError):
            pass
    # Do not call setlocale: changing the process locale can affect other threads.
    for key in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(key)
        if value:
            return normalize_language(value.split(":")[0].split(".")[0])
    try:
        return normalize_language(locale.getlocale()[0])
    except (ValueError, TypeError):
        return "en"


def initialize_language(db, detector):
    """Detect once, atomically; a saved choice always wins, including restarts."""
    with db.connect(write=True) as con:
        row = con.execute(
            "SELECT value FROM settings WHERE key='ui_language'"
        ).fetchone()
        if row is not None:
            if row["value"] not in SUPPORTED_LANGUAGES:
                con.execute("UPDATE settings SET value='en' WHERE key='ui_language'")
            return
        choice = detector()
        choice = choice if choice in SUPPORTED_LANGUAGES else "en"
        con.execute(
            "INSERT INTO settings(key,value) VALUES ('ui_language',?)", (choice,)
        )


def register_i18n(app, db):
    detector = app.config.get("UI_LANGUAGE_DETECTOR")
    initialize_language(
        db,
        detector
        or (lambda: detect_system_language(app.config.get("ANDROID_APP", False))),
    )

    def language():
        if not has_request_context():
            return "en"
        if "ui_language" not in g:
            rows = db.query("SELECT value FROM settings WHERE key='ui_language'")
            choice = rows[0]["value"] if rows else "en"
            g.ui_language = choice if choice in SUPPORTED_LANGUAGES else "en"
        return g.ui_language

    def translate(message, **values):
        # Call only for known UI labels/messages, never for titles, notes or metadata.
        result = TRANSLATIONS.get(message, message) if language() == "tr" else message
        return result.format_map(values) if values else result

    app.jinja_env.globals["t"] = translate
    app.extensions["i18n"] = {"language": language, "translate": translate}

    @app.context_processor
    def localization_context():
        choice = language()
        return {
            "ui_language": choice,
            "ui_messages": {key: TRANSLATIONS[key] for key in CLIENT_MESSAGES}
            if choice == "tr"
            else {},
        }

    @app.after_request
    def language_header(response):
        if request_is_ui():
            response.headers["Content-Language"] = language()
        return response


def request_is_ui():
    from flask import request

    return request.endpoint not in ("static", "poster_file")
