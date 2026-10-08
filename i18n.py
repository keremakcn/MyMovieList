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
