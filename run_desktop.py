"""Native desktop entry point. Waitress binds before the window is opened."""

import os
import ssl
import sys
import tempfile
import threading
from pathlib import Path

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    _bundled_ca = Path(sys._MEIPASS) / "codex-rejected-cas.pem"
    _default_ca = (
        Path(os.path.dirname(getattr(ssl, "__file__", ""))) / "codex-rejected-cas.pem"
    )
    if _bundled_ca.is_file() and not _default_ca.is_file():
        ssl.__file__ = str(Path(sys._MEIPASS) / "ssl.py")

import webview
from waitress import create_server

from app import create_app
from version import APP_VERSION


def _verify_frozen_exe():
    ssl.create_default_context()
    with tempfile.TemporaryDirectory() as tmp:
        app = create_app(
            {
                "TESTING": True,
                "DATA_DIR": tmp,
                "DATABASE": str(Path(tmp) / "movies.db"),
            }
        )
        try:
            client = app.test_client()
            for route in ("/", "/stats", "/settings"):
                res = client.get(route)
                if res.status_code != 200:
                    raise RuntimeError(f"Route {route} failed with {res.status_code}")
        finally:
            if "cloud" in app.extensions:
                app.extensions["cloud"].close()


if __name__ == "__main__":
    if "--verify-exe" in sys.argv:
        _verify_frozen_exe()
        raise SystemExit(0)
    if "--smoke-test" in sys.argv:
        from desktop_smoke import run_smoke_test

        run_smoke_test()
        raise SystemExit(0)
    # The application factory selects the installed platform's persistent library.
    application = create_app()
    server = create_server(application, host="127.0.0.1", port=0)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()
    try:
        webview.create_window(
            f"MyMovieList v{APP_VERSION}",
            f"http://127.0.0.1:{server.effective_port}",
            width=1280,
            height=860,
            min_size=(760, 600),
        )
        webview.start()
    finally:
        if "cloud" in application.extensions:
            application.extensions["cloud"].close()
        else:
            application.extensions["catalog"].close()
        server.close()
