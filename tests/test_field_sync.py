import json
from datetime import datetime, timedelta, timezone

import pytest

from field_sync import EDITABLE, merge, validate_versions
from personal_data import from_movie
from storage import Database
from sync_store import SyncStore

BASE_TIME = "2026-10-09T10:00:00.000000+00:00"
LATE = "2026-10-09T11:00:00.000000+00:00"
LATER = "2026-10-09T12:00:00.000000+00:00"
NOW = "2026-10-10T12:00:00.000000+00:00"


def record():
    return {
        "status": "Watchlist",
        "rating": None,
        "note": None,
        "favorite": False,
        "watched_date": None,
        "added_at": BASE_TIME,
        "order_key": "00000000000000000001:aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa",
        "deleted_at": None,
        "custom": None,
    }


@pytest.mark.parametrize("local_newer", [True, False])
def test_latest_actual_field_edit_wins_not_upload_order(local_newer):
    base = record()
    ours, theirs = dict(base, note="local draft"), dict(base, note="cloud draft")
    left, right = (LATER, LATE) if local_newer else (LATE, LATER)
    value, clocks, conflict = merge(
        base, ours, theirs, {"note": left}, {"note": right}, now=NOW
    )
    assert not conflict
    assert value["note"] == ("local draft" if local_newer else "cloud draft")
    assert clocks["note"] == LATER


def test_independent_fields_and_original_order_survive():
    base = record()
    value, _, conflict = merge(
        base,
        dict(base, rating=9),
        dict(base, note="another device"),
        {"rating": LATE},
        {"note": LATER},
        now=NOW,
    )
    assert not conflict and value["rating"] == 9 and value["note"] == "another device"
    assert value["order_key"] == base["order_key"]


@pytest.mark.parametrize("clock", [None, LATE, "2099-01-01T00:00:00+00:00"])
def test_unknown_equal_and_future_times_require_recoverable_review(clock):
    base = record()
    value, _, conflict = merge(
        base,
        dict(base, note="local"),
        dict(base, note="remote"),
        {"note": LATE},
        {} if clock is None else {"note": clock},
        now=NOW,
    )
    assert conflict and value is None


@pytest.mark.parametrize("delete_newer", [True, False])
def test_deletion_and_newer_edit_follow_same_order(delete_newer):
    base = record()
    deleted = dict(base, deleted_at=LATE)
    edited = dict(base, note="keep this note")
    a, b = (LATER, LATE) if delete_newer else (LATE, LATER)
    value, clocks, conflict = merge(
        base, edited, deleted, {"note": b}, {"deleted_at": a}, now=NOW
    )
    assert not conflict
    assert (value["deleted_at"] is not None) == delete_newer
    assert value["note"] == "keep this note"
    assert clocks["deleted_at"] == LATER


def test_offsets_are_normalized_before_comparison():
    base = record()
    value, _, conflict = merge(
        base,
        dict(base, rating=8),
        dict(base, rating=9),
        {"rating": "2026-10-09T15:00:00+03:00"},
        {"rating": LATE},
        now=NOW,
    )
    assert not conflict and value["rating"] == 8


def make(tmp_path):
    db = Database(tmp_path / "library.db", "aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa")
    db.migrate()
    mid, _ = db.add_tmdb({"tmdb_id": 603, "title": "The Matrix"})
    return db, SyncStore(db), mid


def test_durable_outbox_keeps_clocks_and_newer_edits_after_ack(tmp_path):
    db, store, mid = make(tmp_path)
    op = store.next_operation()
    frozen = json.loads(op["versions_json"])
    db.update_personal(mid, {"note": "after upload started"})
    assert store.next_operation() == op
    store.acknowledge(op, 1)
    following = store.next_operation()
    assert following["expected_revision"] == 1
    assert json.loads(following["versions_json"])["note"] > frozen["note"]
    assert json.loads(following["data_json"])["note"] == "after upload started"


def test_catalog_hydration_and_noop_save_do_not_change_personal_times(tmp_path):
    db, store, mid = make(tmp_path)
    first = store.export()["field_versions"]
    db.update_personal(mid, {"note": None})
    db.execute(
        "UPDATE movies SET title='Matrix TR',overview='Public plot' WHERE id=?", mid
    )
    db.migrate()
    assert store.export()["field_versions"] == first


def test_upgrade_does_not_invent_recent_legacy_timestamps(tmp_path):
    db, store, mid = make(tmp_path)
    with db.connect(write=True) as con:
        con.execute("DROP TABLE sync_field_state")
    db.migrate()
    assert store.export()["field_versions"][db.movie(mid)["record_key"]] == {}
    db.update_personal(mid, {"rating": 8})
    assert set(store.export()["field_versions"][db.movie(mid)["record_key"]]) == {
        "rating"
    }


def test_resolved_conflict_archives_note_and_export_retains_clocks(tmp_path):
    db, store, mid = make(tmp_path)
    first = store.next_operation()
    store.acknowledge(first, 1)
    db.update_personal(mid, {"note": "local note"})
    local_clock = store.export()["field_versions"][first["record_key"]]["note"]
    remote_clock = (
        datetime.fromisoformat(local_clock) + timedelta(seconds=1)
    ).isoformat(timespec="microseconds")
    remote = dict(json.loads(first["data_json"]), note="remote newer note")
    store.apply_page(
        {
            "protocol": 1,
            "changes": [
                {
                    "record_key": first["record_key"],
                    "revision": 2,
                    "data": remote,
                    "field_versions": {"note": remote_clock},
                }
            ],
            "cursor": 2,
        }
    )
    assert db.movie(mid)["note"] == "remote newer note"
    assert not db.query("SELECT * FROM sync_conflicts")
    document = store.export()
    assert (
        json.loads(document["conflict_versions"][0]["local_json"])["note"]
        == "local note"
    )
    target = Database(tmp_path / "import.db")
    target.migrate()
    other = SyncStore(target)
    other.import_new(document)
    assert other.export()["field_versions"] == document["field_versions"]


def test_new_local_edit_is_later_than_observed_remote_time(tmp_path):
    db, store, mid = make(tmp_path)
    first = store.next_operation()
    store.acknowledge(first, 1)
    future = (datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat(
        timespec="microseconds"
    )
    data = json.loads(first["data_json"])
    store.apply_page(
        {
            "protocol": 1,
            "changes": [
                {
                    "record_key": first["record_key"],
                    "revision": 2,
                    "data": dict(data, rating=8),
                    "field_versions": {"rating": future},
                }
            ],
            "cursor": 2,
        }
    )
    db.update_personal(mid, {"rating": 9})
    assert store.export()["field_versions"][first["record_key"]]["rating"] > future


@pytest.mark.parametrize(
    "value", [{"overview": BASE_TIME}, {"rating": "2026-10-09"}, {"note": None}, []]
)
def test_invalid_versions_are_rejected(value):
    with pytest.raises((ValueError, TypeError)):
        validate_versions(value)


def test_only_user_edited_fields_receive_new_times(tmp_path):
    db, store, mid = make(tmp_path)
    key = db.movie(mid)["record_key"]
    before = store.export()["field_versions"][key]
    db.update_personal(mid, {"rating": 8})
    after = store.export()["field_versions"][key]
    assert {k for k in EDITABLE if before[k] != after[k]} == {"rating"}
    assert from_movie(db.movie(mid))["rating"] == 8
