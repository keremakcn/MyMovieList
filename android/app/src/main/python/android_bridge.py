"""Run the shared library entirely on-device, behind a per-process local token."""

import json
from pathlib import Path
import secrets
import threading

_lock = threading.Lock()
_server = None
_connection = None


def create_android_app(data_directory, token):
    from flask import abort, redirect, request
    from app import create_app

    folder = Path(data_directory) / "library"
    app = create_app({
        "DATA_DIR": str(folder),
        "DATABASE": str(folder / "movies.db"),
        "SESSION_COOKIE_NAME": "movie_watchlist_android",
        "ANDROID_APP": True,
    })

    @app.before_request
    def require_native_session():
        if request.endpoint == "native_bootstrap":
            return None
        if not secrets.compare_digest(request.cookies.get("native_access", "").encode("utf-8"), token.encode("ascii")):
            abort(403)

    @app.get("/_native/start")
    def native_bootstrap():
        if not secrets.compare_digest(request.headers.get("X-Native-Token", "").encode("utf-8"), token.encode("ascii")):
            abort(403)
        response = redirect("/")
        response.set_cookie("native_access", token, httponly=True, samesite="Strict")
        return response

    return app


def start(data_directory):
    global _server, _connection
    from waitress import create_server

    with _lock:
        if _server is None:
            token = secrets.token_urlsafe(32)
            app = create_android_app(data_directory, token)
            _server = create_server(app, host="127.0.0.1", port=0, threads=4)
            threading.Thread(target=_server.run, daemon=True, name="library-http").start()
            _connection = {"url": f"http://127.0.0.1:{_server.effective_port}", "token": token}
        return json.dumps(_connection)
