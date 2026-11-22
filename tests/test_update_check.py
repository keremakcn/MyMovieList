"""Tests for the non-blocking desktop update-check endpoint."""

from app import create_app
from version import APP_VERSION


def _make_client(tmp_path, fetcher=None):
    config = {
        "TESTING": True,
        "DATA_DIR": str(tmp_path),
        "DATABASE": str(tmp_path / "movies.db"),
    }
    if fetcher is not None:
        config["UPDATE_CHECK_FETCHER"] = fetcher
    app = create_app(config)
    return app.test_client()


def test_update_check_detects_newer_release_and_caches(tmp_path):
    calls = []

    def fake_fetch():
        calls.append(1)
        return {
            "tag": "v9.9.9",
            "url": "https://github.com/keremakcn/MyMovieList/releases/latest",
        }

    client = _make_client(tmp_path, fake_fetch)
    first = client.get("/api/update-check")
    assert first.status_code == 200
    assert first.headers.get("Cache-Control") == "no-store"
    body = first.get_json()
    assert body["available"] is True
    assert body["current"] == APP_VERSION
    assert body["latest"] == "9.9.9"
    assert body["url"] == "https://github.com/keremakcn/MyMovieList/releases/latest"

    second = client.get("/api/update-check")
    assert second.status_code == 200
    assert len(calls) == 1


def test_update_check_ignores_same_version_and_rejects_untrusted_url(tmp_path):
    def fake_fetch():
        return {
            "tag": f"v{APP_VERSION}",
            "url": "https://evil.example/malware.exe",
        }

    client = _make_client(tmp_path, fake_fetch)
    res = client.get("/api/update-check")
    assert res.status_code == 200
    body = res.get_json()
    assert body["available"] is False
    assert body["url"] == "https://github.com/keremakcn/MyMovieList/releases/latest"


def test_update_check_fails_open_when_offline(tmp_path):
    def broken_fetch():
        raise OSError("offline")

    client = _make_client(tmp_path, broken_fetch)
    res = client.get("/api/update-check")
    assert res.status_code == 200
    body = res.get_json()
    assert body["available"] is False
    assert body["latest"] is None
