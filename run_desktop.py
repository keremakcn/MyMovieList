"""Native desktop entry point. Waitress binds before the window is opened."""

import threading
import webview
from waitress import create_server
from app import create_app

if __name__ == "__main__":
    server = create_server(create_app(), host="127.0.0.1", port=0)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()
    try:
        webview.create_window(
            "Movie Watchlist",
            f"http://127.0.0.1:{server.effective_port}",
            width=1280,
            height=860,
            min_size=(760, 600),
        )
        webview.start()
    finally:
        server.close()
