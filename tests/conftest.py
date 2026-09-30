import pytest
from app import create_app


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.delenv("TMDB_ACCESS_TOKEN", raising=False)
    application = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test",
            "DATA_DIR": str(tmp_path),
            "DATABASE": str(tmp_path / "test.db"),
        }
    )
    return application


@pytest.fixture
def client(app):
    return app.test_client()
