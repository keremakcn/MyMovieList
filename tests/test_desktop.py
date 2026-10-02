"""Protect installed library selection when promoting a desktop release."""

import importlib.util
from pathlib import Path
import runpy
import sys
from unittest.mock import Mock

import pytest

from storage import Database
from version import APP_VERSION


@pytest.mark.parametrize("override", [False, True])
def test_packaged_launcher_retains_existing_library(tmp_path, monkeypatch, override):
    root = Path(__file__).resolve().parents[1]
    roaming = tmp_path / "AppData" / "Roaming"
    data = tmp_path / "custom-library" if override else roaming / "MovieWatchlist"
    monkeypatch.setenv("APPDATA", str(roaming))
    monkeypatch.delenv("MOVIE_WATCHLIST_DATA_DIR", raising=False)
    if override:
        monkeypatch.setenv("MOVIE_WATCHLIST_DATA_DIR", str(data))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(root), raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "Downloads" / "MovieWatchlist.exe"))

    original = Database(data / "movies.db")
    original.migrate()
    original.add_tmdb(dict(tmdb_id=603, title="The Matrix", status="Watched",
                           note="Keep this personal note.", rating=9, favorite=1))
    before = original.query("SELECT * FROM movies")
    spec = importlib.util.spec_from_file_location("desktop_release_app", root / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    real_factory = module.create_app
    created = []

    def factory(*args, **kwargs):
        app = real_factory(*args, **kwargs)
        created.append(app)
        return app

    monkeypatch.setattr(module, "create_app", factory)
    monkeypatch.setitem(sys.modules, "app", module)
    window = Mock()
    server = Mock(effective_port=54321)
    waitress = Mock()
    waitress.create_server.return_value = server
    monkeypatch.setitem(sys.modules, "webview", window)
    monkeypatch.setitem(sys.modules, "waitress", waitress)
    runpy.run_path(str(root / "run_desktop.py"), run_name="__main__")

    assert Path(created[0].config["DATABASE"]) == data / "movies.db"
    assert created[0].config["SESSION_COOKIE_NAME"] == "session"
    assert created[0].extensions["db"].query("SELECT * FROM movies") == before
    response = created[0].test_client().get("/")
    assert response.status_code == 200
    assert f"v{APP_VERSION}" in response.get_data(as_text=True)
    window.create_window.assert_called_once()
    assert window.create_window.call_args.args[0] == f"Movie Watchlist v{APP_VERSION}"
    server.close.assert_called_once()
    assert not (tmp_path / "Downloads" / "data").exists()
