import io
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from uuid import uuid4

import pytest
from test_app import mock_tmdb, post

from app import create_app
from cloud_client import CloudError, SupabaseClient
from personal_data import dumps, from_movie
from session_store import SessionStore
from storage import Database
from sync_store import SyncStore

A = "aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa"
B = "bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb"


class MemorySessions:
    persistent = True

    def __init__(self):
        self.value = None

    def load(self):
        return deepcopy(self.value)

    def save(self, value):
        self.value = deepcopy(value)

    def clear(self):
        self.value = None


class FakeCloud:
    def __init__(self):
        self.records, self.receipts, self.revisions = {}, {}, {}
        self.calls = []
        self.offline = False
        self.limited = False
        self.timeout_after_commit = False
        self.profiles = {}
        self.accounts = {"a@example.test", "b@example.test"}
        self.registration_pending = set()
        self.usernames = {}

    def username_health(self):
        self.health()

    def username_status(self, token):
        self.health()
        return {"username": self.usernames.get(token[7:])}

    def claim_username(self, token, username):
        from account_username import normalize_username

        username = normalize_username(username, writing=True)
        current = self.username_status(token)["username"]
        if current:
            status = "claimed" if current == username else "locked"
        elif username in self.usernames.values():
            status = "taken"
        else:
            current, status = username, "claimed"
            self.usernames[token[7:]] = username
        return {"status": status, "username": current}

    def health(self):
        if self.offline:
            raise CloudError(
                "Could not reach the cloud. Your changes are saved on this device."
            )
        if self.limited:
            raise CloudError(
                "Cloud is temporarily limited. Your changes are saved on this device.",
                "limited",
                120,
            )

    def sign_in(self, email, password):
        owner = A if email == "a@example.test" else B
        self.calls.append(("signin", owner))
        return {
            "user_id": owner,
            "email": email,
            "access_token": "ACCESS-" + owner,
            "refresh_token": "REFRESH-" + owner,
            "expires_in": 3600,
            "profile": deepcopy(
                self.profiles.get(owner, {"display_name": "", "avatar_id": "cat-luna"})
            ),
            "registration_pending": email in self.registration_pending,
        }

    def sign_up(self, email, password):
        self.calls.append(("signup", email))

    def begin_signup(self, email):
        self.health()
        self.calls.append(("begin_signup", email))
        if email not in self.accounts:
            self.accounts.add(email)
            self.registration_pending.add(email)

    def complete_signup(self, token, password):
        self.health()
        self.change_password(token, password)
        owner = token[7:]
        self.registration_pending = {
            email
            for email in self.registration_pending
            if (A if email == "a@example.test" else B) != owner
        }

    def profile(self, token):
        owner = token[7:]
        return {
            "user_id": owner,
            "profile": deepcopy(
                self.profiles.get(owner, {"display_name": "", "avatar_id": "cat-luna"})
            ),
        }

    def update_profile(self, token, profile):
        self.health()
        self.calls.append(("profile", token[7:]))
        self.profiles[token[7:]] = deepcopy(profile)

    def verify(self, email, code, kind="email"):
        self.health()
        if code != "123456":
            raise CloudError("The confirmation code is invalid or expired.", "auth")
        self.calls.append(("verify", kind))
        return self.sign_in(email, "unused")

    def recover(self, email):
        self.calls.append(("recover", email))

    def change_password(self, token, password):
        self.calls.append(("password", token[7:]))

    def sign_out(self, token):
        self.calls.append(("signout", token[7:]))

    def refresh(self, token):
        owner = token[8:]
        self.calls.append(("refresh", owner))
        result = self.sign_in(
            "a@example.test" if owner == A else "b@example.test", "unused"
        )
        return result

    def push(self, token, operation):
        self.health()
        owner = token[7:]
        self.calls.append(("push", owner))
        identity = owner, operation["record_key"]
        receipt = owner, operation["operation_id"]
        if receipt in self.receipts:
            return deepcopy(self.receipts[receipt])
        remote = self.records.get(identity)
        if (remote["revision"] if remote else 0) != operation["expected_revision"]:
            return {
                "status": "conflict",
                "record_key": operation["record_key"],
                "remote": deepcopy(remote),
            }
        revision = self.revisions.get(owner, 0) + 1
        self.revisions[owner] = revision
        self.records[identity] = {
            "data": json.loads(operation["data_json"]),
            "revision": revision,
        }
        result = {
            "status": "applied",
            "record_key": operation["record_key"],
            "revision": revision,
        }
        self.receipts[receipt] = result
        if self.timeout_after_commit:
            self.timeout_after_commit = False
            raise CloudError(
                "Could not reach the cloud. Your changes are saved on this device."
            )
        return deepcopy(result)

    def pull(self, token, cursor):
        self.health()
        owner = token[7:]
        records = sorted(
            (
                {
                    "record_key": k,
                    "data": deepcopy(v["data"]),
                    "revision": v["revision"],
                }
                for (u, k), v in self.records.items()
                if u == owner and v["revision"] > cursor
            ),
            key=lambda r: r["revision"],
        )[:25]
        return {
            "protocol": 1,
            "changes": records,
            "cursor": records[-1]["revision"] if records else cursor,
        }


def local(tmp_path, owner=A):
    db = Database(tmp_path / "library.db", owner)
    db.migrate()
    return db, SyncStore(db)


def custom(db, note="original"):
    return db.add_custom(
        {
            "title": "Private custom film",
            "year": 2020,
            "genre": "Drama",
            "status": "Watched",
            "rating": 9,
            "note": note,
            "favorite": 1,
            "watched_date": "2024-01-03",
        }
    )


def test_schema3_migration_and_backup_preserve_order_data(tmp_path):
    import sqlite3

    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as con:
        con.execute(
            "CREATE TABLE movies(id INTEGER PRIMARY KEY,title TEXT,status TEXT,note TEXT,tmdb_id INTEGER,created_at TEXT)"
        )
        con.executemany(
            "INSERT INTO movies VALUES (?,?,?,?,?,?)",
            [
                (5, "First", "Watched", "keep first", 603, "2023-01-01T12:00:00+00:00"),
                (99, "Second", "Watchlist", "keep second", None, None),
            ],
        )
        con.execute("PRAGMA user_version=3")
    db = Database(path)
    db.migrate()
    rows = db.query("SELECT * FROM movies ORDER BY order_key")
    assert [r["id"] for r in rows] == [5, 99]
    assert [r["note"] for r in rows] == ["keep first", "keep second"]
    assert rows[0]["created_at"] == "2023-01-01T12:00:00+00:00"
    assert rows[1]["created_at"] is None
    portable = from_movie(rows[1])
    assert rows[0]["record_key"] == "tmdb:603"
    assert len(list(tmp_path.glob("*.before-v4-*.bak"))) == 1
    identities = [(r["record_key"], r["order_key"]) for r in rows]
    db.migrate()
    assert [
        (r["record_key"], r["order_key"])
        for r in db.query("SELECT * FROM movies ORDER BY order_key")
    ] == identities
    assert from_movie(db.movie(99)) == portable
    db.update_personal(99, {"rating": 8})
    store = SyncStore(db)
    frozen = dict(from_movie(db.movie(99)), favorite=True)
    store.apply_page(
        {
            "protocol": 1,
            "changes": [
                {"record_key": rows[1]["record_key"], "data": frozen, "revision": 1}
            ],
            "cursor": 1,
        }
    )
    assert db.movie(99)["created_at"] is None


def test_frozen_queue_survives_edits_restart_and_ack(tmp_path):
    db, store = local(tmp_path)
    mid = custom(db)
    frozen = store.next_operation()
    db.update_personal(mid, {"note": "new draft"})
    reopened = Database(db.path, A)
    reopened.migrate()
    restarted = SyncStore(reopened)
    assert restarted.next_operation() == frozen
    restarted.acknowledge(frozen, 1)
    assert reopened.movie(mid)["note"] == "new draft"
    next_operation = restarted.next_operation()
    assert next_operation["expected_revision"] == 1
    assert next_operation["operation_id"] != frozen["operation_id"]
    assert json.loads(next_operation["data_json"])["note"] == "new draft"


def test_delete_undo_while_upload_in_flight_keeps_entire_record(tmp_path):
    db, store = local(tmp_path)
    mid = custom(db)
    store.acknowledge(store.next_operation(), 1)
    before = db.movie(mid)
    marker = db.remove(mid)
    frozen = store.next_operation()
    assert json.loads(frozen["data_json"])["deleted_at"] == marker
    assert db.restore(mid, marker)
    store.acknowledge(frozen, 2)
    assert db.movie(mid) == before
    restored = json.loads(store.next_operation()["data_json"])
    assert restored == from_movie(before)


def test_independent_fields_merge_and_competing_notes_keep_versions(tmp_path):
    db, store = local(tmp_path)
    mid = custom(db)
    key = db.movie(mid)["record_key"]
    first = store.next_operation()
    store.acknowledge(first, 1)
    base = json.loads(first["data_json"])
    db.update_personal(mid, {"favorite": 0})
    remote = dict(base, note="cloud edit")
    store.apply_page(
        {
            "protocol": 1,
            "changes": [{"record_key": key, "data": remote, "revision": 2}],
            "cursor": 2,
        }
    )
    assert db.movie(mid)["note"] == "cloud edit" and db.movie(mid)["favorite"] == 0
    merged = store.next_operation()
    assert merged["expected_revision"] == 2
    store.acknowledge(merged, 3)
    db.update_personal(mid, {"note": "my new note"})
    competing = dict(json.loads(merged["data_json"]), note="another device note")
    store.apply_page(
        {
            "protocol": 1,
            "changes": [{"record_key": key, "data": competing, "revision": 4}],
            "cursor": 4,
        }
    )
    assert db.movie(mid)["note"] == "my new note"
    assert store.next_operation() is None
    conflict = db.query("SELECT * FROM sync_conflicts")[0]
    assert json.loads(conflict["remote_json"])["note"] == "another device note"
    db.update_personal(mid, {"note": "latest local draft"})
    with pytest.raises(ValueError):
        store.resolve(key, "local", 3)
    store.resolve(key, "local", 4)
    selected = store.next_operation()
    assert selected["expected_revision"] == 4
    assert json.loads(selected["data_json"])["note"] == "latest local draft"
    archive = store.export()["conflict_versions"]
    assert {"my new note", "latest local draft"} <= {
        json.loads(r["local_json"])["note"] for r in archive
    }


def test_delete_versus_edit_is_conflict_not_resurrection(tmp_path):
    db, store = local(tmp_path)
    mid = custom(db)
    op = store.next_operation()
    store.acknowledge(op, 1)
    db.update_personal(mid, {"note": "edited offline"})
    removed = dict(json.loads(op["data_json"]), deleted_at="2026-10-07T00:00:00+00:00")
    store.apply_page(
        {
            "protocol": 1,
            "changes": [
                {"record_key": op["record_key"], "data": removed, "revision": 2}
            ],
            "cursor": 2,
        }
    )
    assert db.movie(mid)["note"] == "edited offline"
    assert store.next_operation() is None
    assert len(db.query("SELECT * FROM sync_conflicts")) == 1
    store.resolve(op["record_key"], "remote", 2)
    assert db.movie(mid) is None
    assert store.pending() == 0


def test_invalid_download_rolls_back_rows_and_cursor(tmp_path):
    db, store = local(tmp_path)
    mid = custom(db)
    store.acknowledge(store.next_operation(), 1)
    before = db.movie(mid)
    record = {
        "record_key": before["record_key"],
        "data": dict(from_movie(before), note="remote"),
        "revision": 2,
    }
    with pytest.raises(ValueError):
        store.apply_page({"protocol": 1, "changes": [record, record], "cursor": 2})
    assert db.movie(mid) == before and store.cursor() == 0


def test_export_import_round_trip_and_atomic_invalid_import(tmp_path):
    db, store = local(tmp_path / "one", None)
    mid = custom(db, note="ş\n<script>private</script>")
    db.remove(mid)
    db.add_tmdb(
        {
            "title": "The Matrix",
            "tmdb_id": 603,
            "status": "Watchlist",
            "overview": "PUBLIC DESCRIPTION",
            "cast_list": "PUBLIC CAST",
        }
    )
    document = store.export()
    raw = dumps(document)
    assert "PUBLIC DESCRIPTION" not in raw and "PUBLIC CAST" not in raw
    target, other = local(tmp_path / "two", None)
    assert other.import_new(document) == (2, 0)
    assert other.export()["records"] == document["records"]
    assert other.import_new(document) == (0, 2)
    assert target.query("SELECT COUNT(*) n FROM movies")[0]["n"] == 2
    malformed = deepcopy(document)
    malformed["records"].append(
        {
            "record_key": "custom:" + str(uuid4()),
            "data": dict(document["records"][0]["data"], rating=99),
        }
    )
    with pytest.raises(ValueError):
        other.import_new(malformed)
    assert target.query("SELECT COUNT(*) n FROM movies")[0]["n"] == 2


def test_conflict_archive_export_import_round_trip(tmp_path):
    db, store = local(tmp_path / "one")
    mid = custom(db)
    frozen = store.next_operation()
    store.acknowledge(frozen, 1)
    db.update_personal(mid, {"note": "local"})
    store.apply_page(
        {
            "protocol": 1,
            "changes": [
                {
                    "record_key": frozen["record_key"],
                    "revision": 2,
                    "data": dict(json.loads(frozen["data_json"]), note="remote"),
                }
            ],
            "cursor": 2,
        }
    )
    document = store.export()
    _, target = local(tmp_path / "two", None)
    target.import_new(document)
    assert target.export()["conflict_versions"] == document["conflict_versions"]


@pytest.fixture
def account_app(tmp_path):
    fake = FakeCloud()
    vault = MemorySessions()
    app = create_app(
        {
            "TESTING": True,
            "DATA_DIR": str(tmp_path),
            "DATABASE": str(tmp_path / "guest.db"),
            "SECRET_KEY": "synthetic-test",
            "UI_LANGUAGE_DETECTOR": lambda: "en",
            "CLOUD_CLIENT": fake,
            "CLOUD_SESSION_STORE": vault,
            "CLOUD_ACCOUNTS_READY": True,
        }
    )
    mock_tmdb(app)
    yield app, fake, vault
    app.extensions["cloud"].close()


def login(client, email="a@example.test"):
    return post(client, "/account/signin", email=email, password="test-password")


def test_login_guest_adoption_two_account_isolation_and_csrf(account_app):
    app, _fake, vault = account_app
    client, second = app.test_client(), app.test_client()
    guest = app.extensions["cloud"].guest
    custom(guest, note="guest private")
    original = guest.query("SELECT * FROM movies")
    assert login(client).status_code == 303
    account_a = app.extensions["cloud"].active().db
    assert account_a.query("SELECT * FROM movies") == []
    assert app.extensions["cloud"].enabled(app.extensions["cloud"].active())
    assert post(client, "/account/adopt-local", confirm="yes").status_code == 303
    assert account_a.query("SELECT note FROM movies")[0]["note"] == "guest private"
    assert guest.query("SELECT * FROM movies") == original
    client.get("/account")
    with client.session_transaction() as session:
        stale = session["csrf_token"]
    assert login(second, "b@example.test").status_code == 303
    assert app.extensions["db"].query("SELECT * FROM movies") == []
    response = client.post(
        "/add", data={"title": "stale page"}, headers={"X-CSRF-Token": stale}
    )
    assert response.status_code == 400
    assert app.extensions["db"].query("SELECT * FROM movies") == []
    assert post(second, "/account/signout").status_code == 303
    assert app.extensions["db"].query("SELECT * FROM movies") == original
    assert vault.load() is None
    assert account_a.query("SELECT note FROM movies")[0]["note"] == "guest private"


def test_sync_consent_timeout_replay_quota_and_offline_library(account_app):
    app, fake, _vault = account_app
    client = app.test_client()
    login(client)
    assert post(client, "/account/sync-settings", enabled="1").status_code == 422
    assert (
        post(client, "/account/sync-settings", enabled="1", consent="yes").status_code
        == 303
    )
    db = app.extensions["cloud"].active().db
    mid = custom(db)
    fake.timeout_after_commit = True
    cloud = app.extensions["cloud"]
    cloud.run_once()
    pending = SyncStore(db).next_operation()
    assert pending and len(fake.records) == 1
    assert b"Private custom film" in client.get("/").data
    assert "ACCESS-" not in client.get("/account").get_data(as_text=True)
    assert "REFRESH-" not in client.get("/account/export").get_data(as_text=True)
    cloud.states[A]["retry_at"] = 0
    cloud.run_once()
    assert SyncStore(db).pending() == 0 and len(fake.records) == 1
    db.update_personal(mid, {"rating": 10})
    fake.limited = True
    cloud.run_once()
    assert SyncStore(db).pending() == 1 and db.movie(mid)["rating"] == 10
    assert cloud.states[A]["retry_at"] > 0
    assert client.get("/").status_code == 200
    fake.limited = False
    fake.offline = True
    cloud.states[A]["retry_at"] = 0
    cloud.run_once()
    assert db.movie(mid)["rating"] == 10
    fake.offline = False
    cloud.states[A]["retry_at"] = 0
    cloud.run_once()
    assert SyncStore(db).pending() == 0


def test_signup_verify_reset_ui_never_echo_password_and_account_language_is_device_setting(
    account_app,
):
    app, fake, vault = account_app
    client = app.test_client()
    secret = "DO-NOT-ECHO-ME"
    assert post(client, "/account/signup", email="new@example.test").status_code == 303
    assert post(client, "/account/verify", code="123456").status_code == 303
    assert (
        post(client, "/account/register-username", username="new_member").status_code
        == 303
    )
    assert vault.load() is None
    failed = post(
        client,
        "/account/create-password",
        new_password=secret,
        confirm_password="different",
    )
    assert failed.status_code == 422 and secret.encode() not in failed.data
    assert (
        post(
            client,
            "/account/create-password",
            new_password=secret,
            confirm_password=secret,
        ).status_code
        == 303
    )
    assert vault.load()["user_id"] == B
    assert app.extensions["cloud"].enabled(app.extensions["cloud"].active())
    assert post(client, "/settings/language", language="tr").status_code == 303
    assert (
        app.extensions["cloud"].guest.query(
            "SELECT value FROM settings WHERE key='ui_language'"
        )[0]["value"]
        == "tr"
    )
    assert post(client, "/account/recover", email="new@example.test").status_code == 303
    assert post(client, "/account/verify-reset", code="123456").status_code == 303
    assert (
        post(
            client, "/account/reset", new_password=secret, confirm_password=secret
        ).status_code
        == 303
    )
    assert ("password", B) in fake.calls
    assert vault.load() is None


@pytest.mark.parametrize("language", ["en", "tr"])
@pytest.mark.parametrize("failure_stage", ["verify", "change_password"])
@pytest.mark.parametrize("kind", ["offline", "limited"])
def test_reset_connection_errors_do_not_claim_password_was_saved_locally(
    account_app, monkeypatch, language, failure_stage, kind
):
    app, fake, vault = account_app
    app.extensions["cloud"].guest.execute(
        "INSERT OR REPLACE INTO settings VALUES ('ui_language',?)", language
    )
    client = app.test_client()
    assert post(client, "/account/recover", email="a@example.test").status_code == 303
    if failure_stage == "change_password":
        assert post(client, "/account/verify-reset", code="123456").status_code == 303

    def fail(*args, **kwargs):
        raise CloudError(
            "Could not reach the cloud. Your changes are saved on this device.", kind
        )

    monkeypatch.setattr(fake, failure_stage, fail)
    secret = "NEVER-ECHO-RESET-PASSWORD"
    if failure_stage == "verify":
        response = post(client, "/account/verify-reset", code="123456")
    else:
        response = post(
            client, "/account/reset", new_password=secret, confirm_password=secret
        )
    text = response.get_data(as_text=True)
    assert response.status_code == 422
    if language == "tr":
        assert "Hesap hizmeti" in text or "Hesap hizmetine" in text
        assert "Değişikliklerin bu cihazda kayıtlı" not in text
        assert "Şifre güncellendi" not in text
    else:
        assert "account service" in text or "Account service" in text
        assert "Your changes are saved on this device" not in text
        assert "Password updated" not in text
    assert secret not in text
    assert vault.load() is None


def test_import_export_routes_and_markup(account_app):
    app, _, _ = account_app
    client = app.test_client()
    custom(app.extensions["db"], note="<script>alert(1)</script>")
    exported = client.get("/account/export")
    assert (
        exported.status_code == 200
        and "attachment" in exported.headers["Content-Disposition"]
    )
    assert exported.json["records"][0]["data"]["note"] == "<script>alert(1)</script>"
    assert (
        post(
            client,
            "/account/import",
            library_file=(io.BytesIO(b"broken"), "library.json"),
        ).status_code
        == 422
    )
    assert client.get("/account").status_code == 200
    assert len(app.extensions["db"].query("SELECT * FROM movies")) == 1


def test_feature_stays_disabled_until_external_setup(app, client):
    app.extensions["cloud"].ready = False
    html = client.get("/account").data
    assert b"Cloud accounts are being prepared" in html
    assert (
        post(
            client, "/account/signin", email="a@example.test", password="test-password"
        ).status_code
        == 422
    )
    assert app.extensions["cloud"].selected is None


def test_workspace_switch_during_upload_cannot_write_another_owner(account_app):
    app, fake, _ = account_app
    client = app.test_client()
    login(client)
    post(client, "/account/sync-settings", enabled="1", consent="yes")
    cloud = app.extensions["cloud"]
    db_a = cloud.active().db
    custom(db_a)
    entered, release = threading.Event(), threading.Event()
    push = fake.push

    def slow(token, operation):
        entered.set()
        assert release.wait(3)
        return push(token, operation)

    fake.push = slow
    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(cloud.run_once)
        assert entered.wait(3)
        login(client, "b@example.test")
        release.set()
        running.result(timeout=5)
    assert cloud.selected == B
    assert cloud.active().db.query("SELECT * FROM movies") == []
    assert all(owner == A for owner, _ in fake.records)
    assert db_a.query("SELECT COUNT(*) n FROM movies")[0]["n"] == 1


def test_supabase_adapter_rejects_privileged_keys_and_foreign_endpoints():
    for url in [
        "http://project.supabase.co",
        "https://evil.test",
        "https://project.supabase.co@evil.test",
        "https://project.supabase.co/path",
    ]:
        with pytest.raises(ValueError):
            SupabaseClient(url, "sb_publishable_test")
    for key in ["sb_secret_test", "service_role", "eyJlongLegacyToken"]:
        with pytest.raises(ValueError):
            SupabaseClient("https://project.supabase.co", key)


def test_windows_session_is_sealed_not_plaintext_and_clearable(tmp_path):
    import sys

    if sys.platform != "win32":
        pytest.skip("Windows DPAPI test")
    value = {
        "user_id": A,
        "refresh_token": "PRIVATE-REFRESH",
        "access_token": "PRIVATE-ACCESS",
    }
    store = SessionStore(tmp_path)
    store.save(value)
    assert b"PRIVATE-REFRESH" not in store.path.read_bytes()
    assert SessionStore(tmp_path).load() == value
    store.clear()
    assert not store.path.exists() and store.load() is None


def test_personal_write_and_queue_rollback_together(tmp_path, monkeypatch):
    db, store = local(tmp_path)
    mid = custom(db)
    store.acknowledge(store.next_operation(), 1)
    before = db.movie(mid)

    def fail(con, movie_id):
        con.execute("INSERT INTO sync_dirty VALUES (?)", (before["record_key"],))
        raise OSError("synthetic transaction interruption")

    monkeypatch.setattr(db, "changed", fail)
    with pytest.raises(OSError):
        db.update_personal(mid, {"note": "must not commit"})
    assert db.movie(mid) == before
    assert store.pending() == 0


def test_old_page_cannot_fetch_another_account_status(account_app):
    app, _, _ = account_app
    client = app.test_client()
    login(client)
    stale = app.extensions["cloud"].scope()
    login(client, "b@example.test")
    response = client.get("/api/account/status", headers={"X-Library-Scope": stale})
    assert response.status_code == 409
    assert b"b@example.test" not in response.data


def test_malformed_sealed_session_keeps_account_library_but_requires_login(account_app):
    from cloud_sync import CloudWorkspace

    app, _, vault = account_app
    login(app.test_client())
    custom(app.extensions["cloud"].active().db, note="kept")
    vault.value = {"user_id": A, "access_token": "missing refresh and expiry"}
    reopened = CloudWorkspace(
        app, app.extensions["cloud"].guest, app.extensions["tmdb"]
    )
    try:
        assert reopened.selected == A and reopened.session is None
        assert (
            reopened.active().db.query("SELECT note FROM movies")[0]["note"] == "kept"
        )
    finally:
        reopened.close()


def test_failed_session_save_does_not_replace_memory_or_disk(tmp_path, monkeypatch):
    import sys

    monkeypatch.setattr(sys, "platform", "win32")
    store = SessionStore(tmp_path)
    monkeypatch.setattr(SessionStore, "persistent", property(lambda self: True))
    monkeypatch.setattr(store, "seal", lambda raw, decrypt=False: raw)
    store.save({"old": "session"})
    before = store.path.read_bytes()

    def fail(*args):
        raise OSError("synthetic sealing failure")

    monkeypatch.setattr(store, "seal", fail)
    with pytest.raises(OSError):
        store.save({"new": "session"})
    assert store.load() == {"old": "session"}
    assert store.path.read_bytes() == before


def test_refresh_does_not_block_offline_reads_or_revive_logged_out_session(account_app):
    app, fake, vault = account_app
    client = app.test_client()
    login(client)
    cloud = app.extensions["cloud"]
    cloud.session["expires_at"] = 1
    entered, release = threading.Event(), threading.Event()
    refresh = fake.refresh

    def slow(token):
        entered.set()
        assert release.wait(3)
        return refresh(token)

    fake.refresh = slow
    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(cloud.token, A)
        assert entered.wait(3)
        assert client.get("/").status_code == 200
        cloud.sign_out()
        release.set()
        with pytest.raises(CloudError):
            running.result(timeout=5)
    assert cloud.selected is None and cloud.session is None and vault.load() is None


def test_second_device_restores_personal_data_without_public_metadata_and_merges(
    account_app, tmp_path
):
    app, fake, _ = account_app
    first = app.test_client()
    login(first)
    post(first, "/account/sync-settings", enabled="1", consent="yes")
    source = app.extensions["cloud"].active()
    source.db.add_tmdb(
        {
            "title": "The Matrix",
            "tmdb_id": 603,
            "status": "Watched",
            "rating": 9,
            "note": "private matrix note",
            "favorite": 1,
            "watched_date": "2025-10-01",
            "overview": "public synopsis",
        }
    )
    custom(source.db)
    source_order = [
        r["record_key"]
        for r in source.db.query("SELECT * FROM movies ORDER BY order_key")
    ]
    app.extensions["cloud"].run_once()
    folder = tmp_path / "second-device"
    other = create_app(
        {
            "TESTING": True,
            "DATA_DIR": str(folder),
            "DATABASE": str(folder / "guest.db"),
            "SECRET_KEY": "synthetic-second",
            "UI_LANGUAGE_DETECTOR": lambda: "en",
            "CLOUD_CLIENT": fake,
            "CLOUD_SESSION_STORE": MemorySessions(),
            "CLOUD_ACCOUNTS_READY": True,
        }
    )
    mock_tmdb(other)
    try:
        client = other.test_client()
        login(client)
        post(client, "/account/sync-settings", enabled="1", consent="yes")
        cloud = other.extensions["cloud"]
        cloud.run_once()
        target = cloud.active()
        restored = target.db.query("SELECT * FROM movies WHERE tmdb_id=603")[0]
        original = source.db.query("SELECT * FROM movies WHERE tmdb_id=603")[0]
        assert from_movie(restored) == from_movie(original)
        assert restored["title"] == "TMDB #603" and restored["overview"] is None
        assert [
            r["record_key"]
            for r in target.db.query("SELECT * FROM movies ORDER BY order_key")
        ] == source_order
        fake.offline = True
        assert client.get("/").status_code == 200
        fake.offline = False
        details = target.catalog.details(603)
        target.catalog.fill_missing(603, details)
        assert target.db.movie(restored["id"])["title"] == "The Matrix"
        assert target.db.movie(restored["id"])["note"] == "private matrix note"
        assert target.store.pending() == 0
        target.db.update_personal(restored["id"], {"note": "edit from second device"})
        source.db.update_personal(original["id"], {"rating": 10})
        cloud.run_once()
        app.extensions["cloud"].run_once()
        app.extensions["cloud"].run_once()
        cloud.run_once()
        assert source.db.movie(original["id"])["note"] == "edit from second device"
        assert target.db.movie(restored["id"])["rating"] == 10
        assert source.db.query("SELECT * FROM sync_conflicts") == []
        marker = source.db.remove(original["id"])
        app.extensions["cloud"].run_once()
        cloud.run_once()
        assert target.db.movie(restored["id"]) is None
        assert source.db.restore(original["id"], marker)
        app.extensions["cloud"].run_once()
        cloud.run_once()
        assert target.db.movie(restored["id"])["note"] == "edit from second device"
        assert [
            r["record_key"]
            for r in target.db.query("SELECT * FROM movies ORDER BY order_key")
        ] == source_order
    finally:
        other.extensions["cloud"].close()


class StubResponse(io.BytesIO):
    pass


@pytest.mark.parametrize(
    "configuration",
    [
        "broken-json",
        json.dumps(
            {
                "url": "https://invalid.test",
                "publishable_key": "sb_secret_invalid",
                "accounts_enabled": True,
            }
        ),
    ],
    ids=["invalid-json", "invalid-client"],
)
def test_invalid_cloud_config_cannot_break_guest_library(
    tmp_path, monkeypatch, configuration
):
    from pathlib import Path

    original = Path.read_text

    def read(path, *args, **kwargs):
        return (
            configuration
            if path.name == "project.json"
            else original(path, *args, **kwargs)
        )

    monkeypatch.setattr(Path, "read_text", read)
    app = create_app(
        {
            "TESTING": True,
            "DATA_DIR": str(tmp_path),
            "DATABASE": str(tmp_path / "guest.db"),
            "SECRET_KEY": "synthetic-config",
            "UI_LANGUAGE_DETECTOR": lambda: "en",
            "CLOUD_SESSION_STORE": MemorySessions(),
        }
    )
    try:
        custom(app.extensions["cloud"].guest)
        assert app.test_client().get("/").status_code == 200
        assert not app.extensions["cloud"].ready
    finally:
        app.extensions["cloud"].close()


class StubOpener:
    def __init__(self, raw=b"{}", error=None):
        self.raw, self.error = raw, error
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        if self.error:
            raise self.error
        return StubResponse(self.raw)


def test_http_adapter_uses_https_and_authorization_only_for_authenticated_rpc():
    opener = StubOpener(b'{"service":"mymovielist-sync","protocol":1}')
    adapter = SupabaseClient(
        "https://example.supabase.co", "sb_publishable_test", opener
    )
    adapter.health()
    request, timeout = opener.requests[0]
    assert (
        request.full_url == "https://example.supabase.co/rest/v1/rpc/mml_cloud_status"
    )
    assert request.get_header("Apikey") == "sb_publishable_test"
    assert request.get_header("Authorization") is None and timeout == 12
    adapter.pull("PRIVATE-TOKEN", 4)
    request, _ = opener.requests[-1]
    assert request.get_header("Authorization") == "Bearer PRIVATE-TOKEN"
    assert json.loads(request.data) == {"p_cursor": 4, "p_limit": 25}


@pytest.mark.parametrize(
    "status,payload,kind",
    [
        (429, {"message": "PRIVATE-SUBMITTED-DATA"}, "limited"),
        (402, {}, "limited"),
        (401, {}, "auth"),
        (404, {"code": "PGRST202"}, "setup"),
        (500, {"message": "PRIVATE-SUBMITTED-DATA"}, "offline"),
        (500, [], "offline"),
        (400, {"error_code": "email_address_not_authorized"}, "email"),
    ],
)
def test_http_errors_are_redacted_and_retry_after_is_bounded(status, payload, kind):
    from urllib.error import HTTPError

    error = HTTPError(
        "https://example.supabase.co",
        status,
        "failure",
        {"Retry-After": "999999"},
        io.BytesIO(json.dumps(payload).encode()),
    )
    client = SupabaseClient(
        "https://example.supabase.co", "sb_publishable_test", StubOpener(error=error)
    )
    with pytest.raises(CloudError) as raised:
        client.request("/rest/v1/rpc/test", {})
    assert raised.value.kind == kind and raised.value.retry_after <= 1800
    assert "PRIVATE-SUBMITTED-DATA" not in str(raised.value)


@pytest.mark.parametrize(
    "raw",
    [b"broken", b"[]", b"null", b'"wrong shape"', b"X" * (5 * 1024 * 1024 + 1)],
    ids=["invalid-json", "array", "null", "string", "oversized"],
)
def test_http_adapter_rejects_malformed_or_oversized_success(raw):
    client = SupabaseClient(
        "https://example.supabase.co", "sb_publishable_test", StubOpener(raw)
    )
    with pytest.raises(CloudError) as raised:
        client.request("/rest/v1/rpc/test", {})
    assert raised.value.kind == "protocol"


def test_http_adapter_never_follows_redirect_with_private_token():
    from urllib.request import Request

    from cloud_client import NoRedirect

    request = Request(
        "https://example.supabase.co", headers={"Authorization": "Bearer PRIVATE"}
    )
    assert (
        NoRedirect().redirect_request(
            request, None, 302, "redirect", {}, "https://evil.test"
        )
        is None
    )
