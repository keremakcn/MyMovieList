from urllib.error import URLError

import pytest

from app import create_app


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.delenv("TMDB_ACCESS_TOKEN", raising=False)
    application = create_app(
        {
            "TESTING": True,
            "UI_LANGUAGE_DETECTOR": lambda: "en",
            "SECRET_KEY": "test",
            "DATA_DIR": str(tmp_path),
            "DATABASE": str(tmp_path / "test.db"),
        }
    )

    def offline_provider(*args, **kwargs):
        raise URLError("offline")

    monkeypatch.setattr("tmdb_client.urlopen", offline_provider)
    return application


@pytest.fixture
def client(app):
    return app.test_client()
