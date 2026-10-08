"""Cross-platform regression tests; all credentials and Keychains are synthetic."""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import app as app_module
import i18n
import session_store
from session_store import MAC_SERVICE, MAX_SESSION_BYTES, SessionStore

MAC_KEYCHAIN_FACTORY = session_store.mac_keychain


class FakeKeychain:
    priority = 5

    def __init__(self):
        self.records = {}
        self.fail = False

    def get_password(self, service, account):
        if self.fail:
            raise RuntimeError("Sensitive SDK message PRIVATE-TOKEN")
        return self.records.get((service, account))

    def set_password(self, service, account, value):
        if self.fail:
            raise RuntimeError("Sensitive SDK message " + value)
        self.records[service, account] = value

    def delete_password(self, service, account):
        if self.fail:
            raise RuntimeError("Sensitive SDK message PRIVATE-TOKEN")
        del self.records[service, account]


@pytest.fixture
def keychain(monkeypatch):
    backend = FakeKeychain()
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(session_store, "mac_keychain", lambda: backend)
    return backend


@pytest.mark.parametrize(
    "platform,packaged",
    [("darwin", True), ("win32", True), ("darwin", False), ("win32", False)],
)
def test_installed_data_path_is_independent_of_bundle(
    tmp_path, monkeypatch, platform, packaged
):
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(sys, "frozen", packaged, raising=False)
    monkeypatch.setattr(app_module.Path, "home", lambda: tmp_path / "home")
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    expected = (
        (
            tmp_path / "home/Library/Application Support/MyMovieList"
            if platform == "darwin"
            else tmp_path / "roaming/MovieWatchlist"
        )
        if packaged
        else app_module.BASE_DIR
    )
    assert app_module.default_data_dir() == expected


def test_mac_store_survives_restart_and_logout_without_token_file(tmp_path, keychain):
    value = {"access_token": "SYNTHETIC-ACCESS", "refresh_token": "SYNTHETIC-REFRESH"}
    store = SessionStore(tmp_path)
    assert store.persistent and store.uses_keychain
    store.save(value)
    assert not store.path.exists()
    assert json.loads(keychain.records[MAC_SERVICE, store.mac_account]) == value
    assert SessionStore(tmp_path).load() == value
    store.clear()
    assert SessionStore(tmp_path).load() is None and not keychain.records


def test_mac_test_release_and_custom_folders_do_not_share_sessions(tmp_path, keychain):
    a, b = SessionStore(tmp_path / "release"), SessionStore(tmp_path / "qa")
    a.save({"account": "A"})
    assert SessionStore(tmp_path / "qa").load() is None
    b.save({"account": "B"})
    assert a.mac_account != b.mac_account
    a.clear()
    assert SessionStore(tmp_path / "qa").load() == {"account": "B"}


def test_canonical_mac_folder_keeps_session_when_application_moves(tmp_path, keychain):
    SessionStore(tmp_path / "a/../library").save({"same": "session"})
    assert SessionStore(tmp_path / "library").load() == {"same": "session"}


def test_failed_mac_save_retains_previous_session_and_redacts_sdk_error(
    tmp_path, keychain
):
    store = SessionStore(tmp_path)
    store.save({"old": "session"})
    before = dict(keychain.records)
    keychain.fail = True
    with pytest.raises(OSError) as error:
        store.save({"access_token": "PRIVATE-TOKEN"})
    assert "PRIVATE-TOKEN" not in str(error.value) and error.value.__suppress_context__
    assert store.load() == {"old": "session"} and keychain.records == before
    assert not store.path.exists()


def test_locked_keychain_startup_and_logout_keep_library_files(tmp_path, keychain):
    library = tmp_path / "movies.db"
    library.write_bytes(b"SYNTHETIC DATABASE")
    keychain.fail = True
    store = SessionStore(tmp_path)
    assert store.load() is None
    with pytest.raises(OSError, match="operating system"):
        store.clear()
    assert library.read_bytes() == b"SYNTHETIC DATABASE" and store.memory is None


@pytest.mark.parametrize(
    "raw",
    ["not-json", "[]", "null", '"string"', "a" * (MAX_SESSION_BYTES + 1)],
    ids=["invalid-json", "array", "null", "string", "oversized"],
)
def test_invalid_keychain_record_requires_login(tmp_path, keychain, raw):
    store = SessionStore(tmp_path)
    keychain.records[MAC_SERVICE, store.mac_account] = raw
    assert store.load() is None


def test_oversized_mac_session_never_replaces_previous_value(tmp_path, keychain):
    store = SessionStore(tmp_path)
    store.save({"old": "session"})
    with pytest.raises(OSError, match="too large"):
        store.save({"token": "ş" * MAX_SESSION_BYTES})
    assert SessionStore(tmp_path).load() == {"old": "session"}


def test_android_keystore_takes_precedence_over_mac_runtime_flag(
    tmp_path, keychain, monkeypatch
):
    store = SessionStore(tmp_path, android=True)
    monkeypatch.setattr(store, "seal", lambda raw, decrypt=False: raw)
    store.save({"android": "session"})
    assert store.persistent and not store.uses_keychain
    assert store.path.exists() and not keychain.records


def test_mac_backend_is_explicit_and_does_not_consult_plugins(monkeypatch):
    backend = FakeKeychain()
    factory = Mock(return_value=backend)
    monkeypatch.setitem(
        sys.modules, "keyring.backends.macOS", SimpleNamespace(Keyring=factory)
    )
    assert MAC_KEYCHAIN_FACTORY() is backend
    factory.assert_called_once_with()


def test_unavailable_native_backend_rejects_secure_storage(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "keyring.backends.macOS",
        SimpleNamespace(Keyring=lambda: SimpleNamespace(priority=0)),
    )
    with pytest.raises(OSError, match="unavailable"):
        MAC_KEYCHAIN_FACTORY()


def test_missing_keychain_sdk_never_creates_a_token_file(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")

    def unavailable():
        raise ImportError("Synthetic missing SDK")

    monkeypatch.setattr(session_store, "mac_keychain", unavailable)
    store = SessionStore(tmp_path)
    assert store.load() is None
    with pytest.raises(OSError, match="operating system"):
        store.save({"access_token": "SYNTHETIC-TOKEN"})
    assert store.memory is None and not store.path.exists()


@pytest.mark.parametrize(
    "preferred,expected",
    [(["tr-TR", "en-US"], "tr"), (["en-US", "tr-TR"], "en"), (["de-DE"], "en")],
)
def test_mac_uses_ui_language_before_shell_locale(monkeypatch, preferred, expected):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    native = Mock(return_value=preferred)
    monkeypatch.setitem(
        sys.modules,
        "Foundation",
        SimpleNamespace(NSLocale=SimpleNamespace(preferredLanguages=native)),
    )
    assert i18n.detect_system_language() == expected
    native.assert_called_once_with()


@pytest.mark.parametrize(
    "preferred", [[], RuntimeError("Synthetic unavailable locale")]
)
def test_mac_language_falls_back_when_native_preferences_are_unavailable(
    monkeypatch, preferred
):
    monkeypatch.setattr(sys, "platform", "darwin")
    for name in ("LANGUAGE", "LC_ALL", "LC_MESSAGES"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LANG", "tr_TR.UTF-8")
    native = (
        Mock(side_effect=preferred)
        if isinstance(preferred, Exception)
        else Mock(return_value=preferred)
    )
    monkeypatch.setitem(
        sys.modules,
        "Foundation",
        SimpleNamespace(NSLocale=SimpleNamespace(preferredLanguages=native)),
    )
    assert i18n.detect_system_language() == "tr"


@pytest.mark.parametrize("platform,label", [("darwin", "⌘ K"), ("win32", "Ctrl K")])
def test_shortcut_label_matches_platform(app, monkeypatch, platform, label):
    monkeypatch.setattr(sys, "platform", platform)
    assert f"<kbd>{label}</kbd>" in app.test_client().get("/").get_data(as_text=True)


def test_mac_explicit_data_directory_retains_existing_fields(
    tmp_path, keychain, monkeypatch
):
    folder = tmp_path / "override"
    monkeypatch.setenv("MOVIE_WATCHLIST_DATA_DIR", str(folder))
    application = app_module.create_app(
        {"TESTING": True, "UI_LANGUAGE_DETECTOR": lambda: "en"}
    )
    try:
        guest = application.extensions["cloud"].guest
        guest.add_tmdb(
            {
                "tmdb_id": 603,
                "title": "The Matrix",
                "status": "Watched",
                "rating": 9,
                "favorite": 1,
                "note": "Keep note",
            }
        )
        original = guest.query("SELECT * FROM movies")
        reopened = app_module.create_app({"TESTING": True})
        try:
            assert Path(reopened.config["DATABASE"]) == folder / "movies.db"
            assert (
                reopened.extensions["cloud"].guest.query("SELECT * FROM movies")
                == original
            )
        finally:
            reopened.extensions["cloud"].close()
    finally:
        application.extensions["cloud"].close()


def test_macos_build_refuses_cross_platform_before_mutation(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "mac_builder", Path(__file__).resolve().parents[1] / "scripts/build_macos.py"
    )
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    monkeypatch.setattr(sys, "platform", "win32")
    with pytest.raises(RuntimeError, match="must be built on macOS"):
        builder.build("arm64")


def test_packaged_smoke_rejects_nonempty_folder_before_database_access(
    tmp_path, monkeypatch
):
    from desktop_smoke import run_smoke_test

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("MOVIE_WATCHLIST_DATA_DIR", str(tmp_path))
    library = tmp_path / "movies.db"
    library.write_bytes(b"MUST NOT TOUCH")
    with pytest.raises(RuntimeError, match="empty test directory"):
        run_smoke_test()
    assert library.read_bytes() == b"MUST NOT TOUCH"


def test_mac_social_and_bilingual_setup_without_cloud_dependency(tmp_path, keychain):
    application = app_module.create_app(
        {
            "TESTING": True,
            "DATA_DIR": str(tmp_path),
            "DATABASE": str(tmp_path / "guest.db"),
            "UI_LANGUAGE_DETECTOR": lambda: "en",
            "PUBLIC_PROFILES_READY": False,
            "BACKGROUND_METADATA": False,
        }
    )
    try:
        client = application.test_client()
        assert client.get("/social").status_code == 503
        assert b"Social is being prepared." in client.get("/social").data
        with client.session_transaction() as browser:
            token = browser["csrf_token"]
        assert (
            client.post(
                "/settings/language", data={"csrf_token": token, "language": "tr"}
            ).status_code
            == 303
        )
        social = client.get("/social").get_data(as_text=True)
        assert "Sosyal bölümü hazırlanıyor." in social and "⌘ K" in social
        assert application.extensions["cloud"].guest.query("SELECT * FROM movies") == []
    finally:
        application.extensions["cloud"].close()
