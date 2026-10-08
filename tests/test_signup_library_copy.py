"""New-account onboarding carries the guest library without crossing account boundaries."""

import json

import pytest
from test_app import post
from test_cloud_sync import A, B, account_app as base_account_app, custom, login

from personal_data import from_movie
from storage import utcnow


@pytest.fixture
def account_app(tmp_path):
    yield from base_account_app.__wrapped__(tmp_path)


def seed(app, count=20):
    cloud = app.extensions["cloud"]
    guest = cloud.guest
    if count:
        meta = cloud.active().catalog.details(603)
        guest.add_tmdb(
            dict(
                tmdb_id=603,
                title="The Matrix",
                status="Watched",
                rating=9,
                favorite=1,
                note="Original movie note",
                watched_date="2024-01-03",
                overview=meta["overview"],
                director=meta["director"],
                runtime=meta["runtime"],
                entities_json=json.dumps(meta["entities"]),
                cast_list=", ".join(meta["cast"]),
            )
        )
    for number in range(count - 1):
        mid = custom(guest, f"Private note {number}")
        guest.update_personal(
            mid,
            {
                "status": "Watchlist" if number % 2 else "Watched",
                "rating": number % 10 + 1,
                "favorite": number % 2,
            },
        )
    return guest.query("SELECT * FROM movies ORDER BY id")


def password_step(client):
    assert post(client, "/account/signup", email="new@example.test").status_code == 303
    assert post(client, "/account/verify", code="123456").status_code == 303
    assert (
        post(
            client, "/account/register-username", username="new_cinema_fan"
        ).status_code
        == 303
    )


def finish(client):
    return post(
        client,
        "/account/create-password",
        new_password="synthetic-password",
        confirm_password="synthetic-password",
    )


@pytest.mark.parametrize("count", [0, 20])
def test_new_registration_copies_all_personal_fields_and_offline_metadata(
    account_app, count
):
    app, fake, _ = account_app
    original = seed(app, count)
    cloud, client = app.extensions["cloud"], app.test_client()
    password_step(client)
    assert cloud.selected is None and not fake.records
    assert finish(client).status_code == 303
    target = cloud.active().db
    copied = {r["record_key"]: r for r in target.query("SELECT * FROM movies")}
    assert len(copied) == count
    for row in original:
        assert from_movie(copied[row["record_key"]]) == from_movie(row)
        assert copied[row["record_key"]]["created_at"] == row["created_at"]
    assert cloud.guest.query("SELECT * FROM movies ORDER BY id") == original
    if count:
        movie = next(r for r in copied.values() if r["tmdb_id"] == 603)
        source = next(r for r in original if r["tmdb_id"] == 603)
        for field in ("overview", "director", "runtime", "cast_list", "entities_json"):
            assert movie[field] == source[field]
        assert target.query("SELECT * FROM movie_metadata") == cloud.guest.query(
            "SELECT * FROM movie_metadata"
        )
        fake.offline = True
        cloud.run_once()
        assert cloud.active().store.pending() == count
        assert client.get("/").status_code == 200
        fake.offline = False
        cloud.states[B]["retry_at"] = 0
    cloud.run_once()
    assert cloud.active().store.pending() == 0
    assert all(
        fake.records[(B, row["record_key"])]["data"] == from_movie(row)
        for row in original
    )
    assert all(
        "overview" not in value["data"] and "entities_json" not in value["data"]
        for value in fake.records.values()
    )


@pytest.mark.parametrize("language", ["en", "tr"])
def test_disclosure_is_before_email_and_password_and_not_on_signin_or_recovery(
    account_app, language
):
    app, _, _ = account_app
    seed(app)
    app.extensions["cloud"].guest.execute(
        "INSERT OR REPLACE INTO settings VALUES ('ui_language',?)", language
    )
    client = app.test_client()
    for route in ("/account?flow=signin", "/account?flow=recover"):
        assert b"data-signup-library-copy" not in client.get(route).data
    html = client.get("/account?flow=signup").get_data(as_text=True)
    assert "data-signup-library-copy" in html and "20" in html
    assert (
        "otomatik olarak hesabına kopyalanır" in html
        if language == "tr"
        else "automatically copies" in html
    )
    password_step(client)
    html = client.get("/account?flow=password").get_data(as_text=True)
    assert "data-signup-library-copy" in html and "20" in html
    assert "copied only if you choose" not in html


def test_copy_failure_rolls_back_all_records_before_completing_account(account_app):
    app, fake, vault = account_app
    original = seed(app)
    cloud, client = app.extensions["cloud"], app.test_client()
    password_step(client)
    staged = cloud._library(B)
    staged.db.execute(
        "CREATE TRIGGER reject_cache BEFORE INSERT ON movie_metadata "
        "BEGIN SELECT RAISE(ABORT,'synthetic copy failure'); END"
    )
    response = finish(client)
    assert response.status_code == 422
    assert b"Could not copy your local library" in response.data
    assert not any(call[0] == "password" for call in fake.calls)
    assert not staged.db.query("SELECT * FROM movies")
    assert (
        staged.store.pending() == 0 and vault.load() is None and cloud.selected is None
    )
    assert cloud.guest.query("SELECT * FROM movies ORDER BY id") == original
    staged.db.execute("DROP TRIGGER reject_cache")
    assert finish(client).status_code == 303
    assert len(staged.db.query("SELECT * FROM movies")) == 20


def test_concurrent_source_edit_cannot_mix_personal_and_catalog_snapshots(
    account_app, monkeypatch
):
    from sync_store import SyncStore

    app, _, _ = account_app
    original = seed(app, 1)[0]
    cloud = app.extensions["cloud"]
    with cloud.guest.connect() as con:
        con.execute("PRAGMA journal_mode=WAL")
    export = SyncStore._export

    def edit_between_reads(con):
        document = export(con)
        cloud.guest.update_personal(original["id"], {"note": "New concurrent note"})
        cloud.guest.execute(
            "UPDATE movies SET overview='New concurrent overview' WHERE id=?",
            original["id"],
        )
        return document

    monkeypatch.setattr(SyncStore, "_export", staticmethod(edit_between_reads))
    target = cloud._library(B)
    assert target.store.copy_from(cloud.guest) == (1, 0)
    copied = target.db.query("SELECT * FROM movies")[0]
    assert copied["note"] == original["note"]
    assert copied["overview"] == original["overview"]
    assert cloud.guest.movie(original["id"])["note"] == "New concurrent note"


@pytest.mark.parametrize("failure", ["response_lost", "session_save"])
def test_lost_completion_or_session_failure_still_restores_library_on_later_signin(
    account_app, failure
):
    from cloud_client import CloudError

    app, fake, vault = account_app
    original = seed(app)
    cloud, client = app.extensions["cloud"], app.test_client()
    password_step(client)
    complete, save = fake.complete_signup, vault.save
    if failure == "response_lost":

        def lost_response(*args):
            complete(*args)
            raise CloudError("synthetic network interruption", "offline")

        fake.complete_signup = lost_response
    else:

        def cannot_save(_value):
            raise OSError("synthetic session failure")

        vault.save = cannot_save
    assert finish(client).status_code == 422
    assert cloud.selected is None and vault.load() is None
    assert cloud.guest.query("SELECT * FROM movies ORDER BY id") == original
    fake.complete_signup, vault.save = complete, save
    assert login(client, "new@example.test").status_code == 303
    assert cloud.active().owner == B
    assert len(cloud.active().db.query("SELECT * FROM movies")) == 20
    cloud.run_once()
    assert cloud.active().store.pending() == 0
    assert all(
        fake.records[(B, row["record_key"])]["data"] == from_movie(row)
        for row in original
    )


def test_prepared_copy_retry_and_replayed_submission_never_duplicate(account_app):
    from cloud_client import CloudError

    app, fake, _ = account_app
    seed(app)
    client = app.test_client()
    password_step(client)
    complete = fake.complete_signup

    def failed(*args):
        raise CloudError("synthetic offline", "offline")

    fake.complete_signup = failed
    assert finish(client).status_code == 422
    staged = app.extensions["cloud"]._library(B)
    assert len(staged.db.query("SELECT * FROM movies")) == 20
    fake.complete_signup = complete
    assert finish(client).status_code == 303
    assert finish(client).status_code == 422
    assert len(staged.db.query("SELECT * FROM movies")) == 20
    assert sum(call[0] == "password" for call in fake.calls) == 1


def test_existing_signin_does_not_copy_and_manual_copy_keeps_both_versions(account_app):
    app, _, _ = account_app
    original = seed(app)
    cloud, client = app.extensions["cloud"], app.test_client()
    assert login(client).status_code == 303
    target = cloud.active().db
    assert target.query("SELECT * FROM movies") == []
    assert post(client, "/account/adopt-local", confirm="yes").status_code == 303
    row = target.query("SELECT * FROM movies WHERE tmdb_id=603")[0]
    target.update_personal(row["id"], {"note": "Account version", "rating": 2})
    assert post(client, "/account/adopt-local", confirm="yes").status_code == 303
    assert (
        target.movie(row["id"])["note"] == "Account version"
        and target.movie(row["id"])["rating"] == 2
    )
    assert len(target.query("SELECT * FROM movies")) == 20
    assert cloud.guest.query("SELECT * FROM movies ORDER BY id") == original
    assert b"other versions remain" in client.get("/account/settings").data


def test_signed_in_signup_and_recovery_do_not_auto_copy_guest(account_app):
    app, fake, _ = account_app
    original = seed(app)
    client = app.test_client()
    assert login(client).status_code == 303
    response = post(client, "/account/signup", email="new@example.test")
    assert response.status_code == 422
    assert not any(call[0] == "begin_signup" for call in fake.calls)
    assert post(client, "/account/recover", email="a@example.test").status_code == 303
    assert post(client, "/account/verify-reset", code="123456").status_code == 303
    assert (
        post(
            client,
            "/account/reset",
            new_password="new-password",
            confirm_password="new-password",
        ).status_code
        == 303
    )
    cloud = app.extensions["cloud"]
    assert cloud._library(A).db.query("SELECT * FROM movies") == []
    assert cloud.guest.query("SELECT * FROM movies ORDER BY id") == original


def test_copy_preserves_deleted_films_and_unknown_legacy_creation_date(account_app):
    app, _, _ = account_app
    seed(app, 2)
    cloud, client = app.extensions["cloud"], app.test_client()
    row = cloud.guest.query("SELECT * FROM movies WHERE tmdb_id IS NULL")[0]
    cloud.guest.execute("UPDATE movies SET created_at=NULL WHERE id=?", row["id"])
    marker = cloud.guest.remove(row["id"])
    original = cloud.guest.query("SELECT * FROM movies ORDER BY id")
    password_step(client)
    assert finish(client).status_code == 303
    copied = cloud.active().db.query(
        "SELECT * FROM movies WHERE record_key=?", row["record_key"]
    )[0]
    assert copied["deleted_at"] == marker and copied["created_at"] is None
    assert cloud.active().db.library_stats()["total"] == 1
    assert cloud.guest.query("SELECT * FROM movies ORDER BY id") == original


def test_scope_switch_during_completion_never_copies_into_another_account(account_app):
    app, fake, _ = account_app
    original = seed(app)
    cloud, client = app.extensions["cloud"], app.test_client()
    password_step(client)
    complete = fake.complete_signup

    def switched(*args):
        complete(*args)
        cloud.accept_session(fake.sign_in("a@example.test", "unused"))

    fake.complete_signup = switched
    assert finish(client).status_code == 422
    assert (
        cloud.active().owner == A
        and cloud.active().db.query("SELECT * FROM movies") == []
    )
    assert len(cloud._library(B).db.query("SELECT * FROM movies")) == 20
    assert cloud.guest.query("SELECT * FROM movies ORDER BY id") == original


def test_same_server_movie_with_different_notes_requires_review_and_keeps_server_order(
    account_app,
):
    from uuid import uuid4

    app, fake, _ = account_app
    original = seed(app, 1)
    source = from_movie(original[0])
    old = dict(
        source,
        note="Previously synced account note",
        deleted_at=utcnow(),
        order_key=f"{9:020}:{uuid4()}",
        added_at=utcnow(),
    )
    fake.push(
        "ACCESS-" + B,
        {
            "record_key": original[0]["record_key"],
            "operation_id": str(uuid4()),
            "expected_revision": 0,
            "data_json": json.dumps(old),
        },
    )
    push = fake.push

    def strict_push(token, operation):
        stored = fake.records.get((token[7:], operation["record_key"]))
        if stored and stored["revision"] == operation["expected_revision"]:
            payload = json.loads(operation["data_json"])
            assert payload["order_key"] == stored["data"]["order_key"]
            assert payload["added_at"] == stored["data"]["added_at"]
        return push(token, operation)

    fake.push = strict_push
    client, cloud = app.test_client(), app.extensions["cloud"]
    password_step(client)
    assert finish(client).status_code == 303
    cloud.run_once()
    conflicts = cloud.active().db.query("SELECT * FROM sync_conflicts")
    assert len(conflicts) == 1
    assert json.loads(conflicts[0]["local_json"])["note"] == source["note"]
    assert json.loads(conflicts[0]["remote_json"])["note"] == old["note"]
    assert (
        post(
            client,
            "/account/resolve",
            record_key=original[0]["record_key"],
            choice="local",
            revision=conflicts[0]["remote_revision"],
        ).status_code
        == 303
    )
    cloud.run_once()
    assert cloud.active().store.pending() == 0
    saved = fake.records[(B, original[0]["record_key"])]["data"]
    assert saved["note"] == source["note"] and saved["deleted_at"] is None
    assert (
        saved["order_key"] == old["order_key"] and saved["added_at"] == old["added_at"]
    )
    assert (
        cloud.active().db.query("SELECT COUNT(*) n FROM sync_conflict_archive")[0]["n"]
        >= 2
    )
