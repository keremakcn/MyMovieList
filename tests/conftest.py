import sys
from urllib.error import URLError

import pytest

from app import create_app


@pytest.fixture(autouse=True)
def isolated_mac_keychain(monkeypatch):
    """Unit tests must never read/write the runner's real Keychain."""
    if sys.platform == "darwin":

        class FakeKeychain:
            def __init__(self):
                self.records = {}

            def get_password(self, service, account):
                return self.records.get((service, account))

            def set_password(self, service, account, value):
                self.records[service, account] = value

            def delete_password(self, service, account):
                self.records.pop((service, account), None)

        backend = FakeKeychain()
        monkeypatch.setattr("session_store.mac_keychain", lambda: backend)


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
