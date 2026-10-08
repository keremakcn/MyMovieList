import importlib.util
from pathlib import Path
import secrets

import pytest


@pytest.fixture
def android_app(tmp_path):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "android_bridge", root / "android/app/src/main/python/android_bridge.py"
    )
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)
    token = secrets.token_urlsafe(32)
    app = bridge.create_android_app(tmp_path, token)
    app.config["TESTING"] = True
    yield app, token
    app.extensions["cloud"].close()


def test_android_blocks_other_local_clients(android_app):
    app, token = android_app
    client = app.test_client()
    for path in ["/", "/settings", "/static/style.css", "/_native/start"]:
        assert client.get(path).status_code == 403
    assert client.get("/_native/start", headers={"X-Native-Token": "wrong"}).status_code == 403
    assert client.get("/_native/start", headers={"X-Native-Token": "é"}).status_code == 403
    client.set_cookie("native_access", "é")
    assert client.get("/").status_code == 403
    response = client.get("/_native/start", headers={"X-Native-Token": token})
    assert response.status_code == 302
    cookie = response.headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie
    assert token not in response.headers["Location"]
    assert client.get("/").status_code == 200
    assert client.get("/static/style.css").status_code == 200
    assert app.test_client().get("/").status_code == 403


def test_android_data_is_private_and_survives_restart(android_app, tmp_path):
    app, token = android_app
    assert Path(app.config["DATABASE"]) == tmp_path / "library/movies.db"
    db = app.extensions["db"]
    db.add_tmdb(dict(tmdb_id=603, title="The Matrix", note="Personal note", rating=9, favorite=1))
    before = db.query("SELECT * FROM movies")
    client = app.test_client()
    client.get("/_native/start", headers={"X-Native-Token": token})
    client.get("/")
    # Native authentication supplements CSRF protection; it does not replace it.
    assert client.post("/settings", data={"tmdb_token": "changed"}).status_code == 400
    from storage import Database
    reopened = Database(app.config["DATABASE"])
    reopened.migrate()
    assert reopened.query("SELECT * FROM movies") == before
