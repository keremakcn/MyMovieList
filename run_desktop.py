"""Native desktop entry point. Waitress binds before the window is opened."""

import threading

import webview
from waitress import create_server

from app import create_app
from version import APP_VERSION

if __name__ == "__main__":
    # The application factory retains the installed app's AppData library.
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
