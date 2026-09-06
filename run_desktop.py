"""Desktop entry point for Movie Watchlist.

Runs the Flask app (via waitress) in a background thread, then opens
it in a native window with pywebview -- no browser tabs, no address
bar, just looks like a normal desktop app.

This is the file to point PyInstaller at (not app.py), same pattern
as MyGameList:

    pyinstaller --noconfirm --onefile --windowed --name MovieWatchlist ^
        --add-data "templates;templates" --add-data "static;static" ^
        run_desktop.py

Note: importing `app` here runs all of app.py's top-level code (Flask
app creation, database setup) but NOT its own `if __name__ ==
"__main__"` block (that only fires when app.py itself is run
directly, e.g. `python app.py` for quick testing without a native
window).
"""

import threading
import time

import webview
from waitress import serve

import app as app_module

HOST = "127.0.0.1"
PORT = 5000


def _start_server():
    serve(app_module.app, host=HOST, port=PORT)


if __name__ == "__main__":
    server_thread = threading.Thread(target=_start_server, daemon=True)
    server_thread.start()

    # Give waitress a moment to actually start listening before the
    # window tries to load the page.
    time.sleep(1)

    webview.create_window(
        "Movie Watchlist",
        f"http://{HOST}:{PORT}",
        width=1280,
        height=860,
        min_size=(900, 600),
    )
    webview.start()