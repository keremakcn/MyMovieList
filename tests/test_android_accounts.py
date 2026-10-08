"""Shared account integration behind the Android wrapper, without real accounts."""

import base64
import importlib.util
import secrets
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import app as app_module
from session_store import SessionStore
from test_app import mock_tmdb, post
from test_cloud_sync import A, FakeCloud, MemorySessions, custom, login


def test_native_account_offline_retry_restart_and_guest_separation(
    tmp_path, monkeypatch
):
    real_factory = app_module.create_app
    fake, vault = FakeCloud(), MemorySessions()

    def factory(config):
        application = real_factory(
            dict(
                config,
                TESTING=True,
                SECRET_KEY="synthetic-android-test",
                BACKGROUND_METADATA=False,
                UI_LANGUAGE_DETECTOR=lambda: "en",
                CLOUD_CLIENT=fake,
                CLOUD_SESSION_STORE=vault,
                CLOUD_ACCOUNTS_READY=True,
            )
        )
        mock_tmdb(application)
        return application

    monkeypatch.setattr(app_module, "create_app", factory)
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "android_bridge_account_test",
        root / "android/app/src/main/python/android_bridge.py",
    )
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)
    first_token = secrets.token_urlsafe(32)
    application = bridge.create_android_app(tmp_path, first_token)
    cloud = application.extensions["cloud"]
    try:
        custom(cloud.guest, note="guest stays private")
        guest_before = cloud.guest.query("SELECT * FROM movies")
        client = application.test_client()
        assert client.get("/account").status_code == 403
        assert (
            client.get(
                "/_native/start", headers={"X-Native-Token": first_token}
            ).status_code
            == 302
        )
        assert login(client).status_code == 303
        account = cloud.active()
        assert account.owner == A and account.db.query("SELECT * FROM movies") == []
        assert cloud.enabled(account)
        mid = custom(account.db, note="account note while offline")
        original = account.db.movie(mid)
        fake.offline = True
        cloud.run_once()
        assert account.store.pending() == 1 and fake.records == {}
        assert client.get("/").status_code == 200
        assert cloud.guest.query("SELECT * FROM movies") == guest_before
        fake.offline = False
        cloud.states[A]["retry_at"] = 0
        cloud.run_once()
        assert account.store.pending() == 0
        assert (
            fake.records[(A, original["record_key"])]["data"]["note"]
            == original["note"]
        )
        assert account.db.movie(mid) == original
        assert vault.load()["user_id"] == A
    finally:
        cloud.close()

    next_token = secrets.token_urlsafe(32)
    restarted = bridge.create_android_app(tmp_path, next_token)
    cloud = restarted.extensions["cloud"]
    try:
        client = restarted.test_client()
        client.set_cookie("native_access", first_token)
        assert client.get("/").status_code == 403
        client.get("/_native/start", headers={"X-Native-Token": next_token})
        assert cloud.active().owner == A
        assert cloud.active().db.movie(mid) == original
        assert post(client, "/account/signout").status_code == 303
        assert cloud.active().owner is None
        assert cloud.guest.query("SELECT * FROM movies") == guest_before
        assert vault.load() is None
    finally:
        cloud.close()


def test_android_session_java_bridge_roundtrip_and_corrupt_session(
    tmp_path, monkeypatch
):
    # This verifies the Python/Java boundary; real Keystore cryptography requires a phone.
    calls = []

    class JavaSessionHelper:
        @staticmethod
        def seal(raw):
            calls.append("seal")
            return base64.b64encode(raw.encode()).decode("ascii")

        @staticmethod
        def open(raw):
            calls.append("open")
            return base64.b64decode(raw, validate=True).decode()

    def jclass(name):
        assert name == "com.moviewatchlist.CloudSessionStore"
        return JavaSessionHelper

    monkeypatch.setitem(sys.modules, "java", SimpleNamespace(jclass=jclass))
    session = {
        "access_token": "SYNTHETIC-TOKEN",
        "refresh_token": "SYNTHETIC-REFRESH",
        "user_id": A,
    }
    SessionStore(tmp_path, android=True).save(session)
    assert SessionStore(tmp_path, android=True).load() == session
    assert calls == ["seal", "open"]
    assert not (tmp_path / "cloud-session.tmp").exists()
    library = tmp_path / "library.db"
    library.write_bytes(b"preserve library")
    (tmp_path / "cloud-session.sealed").write_bytes(b"invalid!session")
    assert SessionStore(tmp_path, android=True).load() is None
    assert library.read_bytes() == b"preserve library"


@pytest.mark.parametrize("action", ["save", "load"])
def test_android_session_bridge_failure_is_redacted(tmp_path, monkeypatch, action):
    def jclass(_name):
        raise RuntimeError("SYNTHETIC-PRIVATE-TOKEN-in-Java-error")

    monkeypatch.setitem(sys.modules, "java", SimpleNamespace(jclass=jclass))
    store = SessionStore(tmp_path, android=True)
    if action == "save":
        with pytest.raises(OSError) as error:
            store.save({"access_token": "SYNTHETIC-PRIVATE-TOKEN"})
        assert "SYNTHETIC-PRIVATE-TOKEN" not in str(error.value)
        assert not store.path.exists() and store.memory is None
    else:
        store.path.write_bytes(b"sealed-placeholder")
        assert store.load() is None
