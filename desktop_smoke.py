"""Opt-in packaged macOS verification with synthetic data, never the user's library."""

import json
import os
import sys
import threading
from pathlib import Path
from urllib.request import urlopen


def run_smoke_test():
    folder = os.environ.get("MOVIE_WATCHLIST_DATA_DIR")
    if sys.platform != "darwin" or not folder:
        raise RuntimeError(
            "The Mac smoke test requires its own explicit data directory."
        )
    # An empty, existing directory is required before any database/Keychain access.
    path = Path(folder).resolve()
    if not path.is_dir() or any(path.iterdir()):
        raise RuntimeError("The Mac smoke test requires an empty test directory.")
    import webview.platforms.cocoa  # noqa: F401 -- verify the bundled native backend.
    from waitress import create_server

    from app import create_app
    from session_store import SessionStore
    from version import APP_VERSION

    app = create_app(
        {
            "TESTING": True,
            "UI_LANGUAGE_DETECTOR": lambda: "en",
            "PUBLIC_PROFILES_READY": False,
        }
    )
    server = None
    store = SessionStore(path)
    try:
        db = app.extensions["cloud"].guest
        db.add_tmdb(
            {
                "tmdb_id": 603,
                "title": "The Matrix",
                "status": "Watched",
                "rating": 9,
                "favorite": 1,
                "note": "Synthetic Mac smoke-test note.",
            }
        )
        original = db.query("SELECT * FROM movies ORDER BY id")
        client = app.test_client()
        settings = client.get("/settings")
        assert settings.status_code == 200 and b'lang="en"' in settings.data
        with client.session_transaction() as browser:
            csrf = browser["csrf_token"]
        assert (
            client.post(
                "/settings/language", data={"language": "tr", "csrf_token": csrf}
            ).status_code
            == 303
        )
        assert b'lang="tr"' in client.get("/settings").data
        social = client.get("/social")
        assert social.status_code == 503
        assert "Sosyal bölümü hazırlanıyor." in social.get_data(as_text=True)
        assert "/social" in social.get_data(as_text=True)
        assert db.query("SELECT * FROM movies ORDER BY id") == original
        server = create_server(app, host="127.0.0.1", port=0)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        with urlopen(
            f"http://127.0.0.1:{server.effective_port}/", timeout=10
        ) as response:
            html = response.read().decode("utf-8")
            assert response.status == 200 and "The Matrix" in html and "⌘ K" in html
        synthetic = {
            "user_id": "00000000-0000-4000-8000-000000000001",
            "access_token": "synthetic-macos-build-test",
            "refresh_token": "synthetic-macos-build-test",
        }
        store.save(synthetic)
        assert SessionStore(path).load() == synthetic
        assert not store.path.exists()
        store.clear()
        assert SessionStore(path).load() is None
        # Reloaded app sees the same data and saved language without re-detection.
        restarted = create_app({"TESTING": True})
        try:
            assert (
                restarted.extensions["cloud"].guest.query(
                    "SELECT * FROM movies ORDER BY id"
                )
                == original
            )
            assert b'lang="tr"' in restarted.test_client().get("/settings").data
        finally:
            restarted.extensions["cloud"].close()
        print(
            json.dumps(
                {
                    "result": "passed",
                    "version": APP_VERSION,
                    "cocoa_backend": True,
                    "social_route_offline": True,
                    "loopback_startup": True,
                    "keychain_roundtrip": True,
                    "session_logout": True,
                    "language_persistence": True,
                    "personal_fields_preserved": True,
                }
            ),
            flush=True,
        )
    finally:
        try:
            store.clear()
        finally:
            app.extensions["cloud"].close()
            if server:
                server.close()
