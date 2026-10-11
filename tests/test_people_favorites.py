from copy import deepcopy

import pytest

from people_favorites import PersonFavorites, validate
from storage import Database
from sync_store import SyncStore
from test_app import mock_tmdb, post
from test_cloud_sync import FakeCloud, MemorySessions, A, B, login
from app import create_app
from cloud_client import CloudError


def store(tmp_path, name="one", owner=A):
    db = Database(tmp_path / (name + ".db"), owner)
    db.migrate()
    return PersonFavorites(db)


def remote(op, revision=1):
    return {
        **{k: v for k, v in op.items() if k != "operation_id"},
        "revision": revision,
    }


def test_roles_removal_and_frozen_retry(tmp_path):
    s = store(tmp_path)
    s.set(6384, "actor", True)
    s.set(6384, "director", True)
    op = s.next_operation()
    assert s.next_operation() == op
    s.set(op["person_id"], op["role"], False)
    s.acknowledge(op, {"status": "applied", "record": remote(op)})
    assert s.pending() == 2
    removal = s.next_operation()
    assert removal["favorite"] is False
    assert removal["edited_at"] > op["edited_at"]
    s.acknowledge(removal, {"status": "applied", "record": remote(removal, 2)})
    assert s.keys() == {"director:6384"}
    other = store(tmp_path, "other")
    other.apply_page({"protocol": 1, "changes": [remote(removal, 2)], "cursor": 2})
    assert other.keys() == set()
    # An old page or receipt cannot reverse a newer removal.
    with other.db.connect(write=True) as con:
        other.receive(con, remote(op), acknowledgement=True)
    assert other.keys() == set()


def test_server_newer_wins_and_equal_revision_ack_clears_pending(tmp_path):
    s = store(tmp_path)
    s.set(6384, "actor", True)
    op = s.next_operation()
    new = {**remote(op), "favorite": False, "edited_at": "2099-01-01T00:00:00Z"}
    s.acknowledge(op, {"status": "applied", "record": new})
    assert not s.pending()
    assert s.keys() == set()
    # A stale offline preference rejected at the existing server revision settles.
    s.db.execute(
        "UPDATE person_favorites SET favorite=1,edited_at='2000-01-01T00:00:00.000000+00:00'"
    )
    op = s.next_operation()
    s.acknowledge(op, {"status": "applied", "record": new})
    assert not s.pending()
    assert s.keys() == set()


def test_guest_copy_export_import_owner_isolation(tmp_path):
    guest = store(tmp_path, "guest", None)
    account = store(tmp_path, "account")
    other = store(tmp_path, "other", B)
    guest.set(6384, "actor", True)
    guest.set(1, "director", True)
    guest.cache(6384, {"name": "Keanu Reeves", "profile_path": "/keanu.jpg"})
    account.set(6384, "actor", False)
    SyncStore(account.db).copy_from(guest.db)
    assert account.keys() == {"director:1"}
    assert guest.keys() == {"actor:6384", "director:1"}
    assert account.metadata(6384)["name"] == "Keanu Reeves"
    document = SyncStore(guest.db).export()
    assert all(
        set(r) == {"person_id", "role", "favorite", "edited_at"}
        for r in document["person_favorites"]
    )
    assert "Keanu" not in str(document)
    SyncStore(other.db).import_new(document)
    assert other.keys() == guest.keys()
    bad = deepcopy(document)
    bad["person_favorites"][0]["person_id"] = True
    with pytest.raises(ValueError):
        SyncStore(other.db).import_new(bad)


def test_invalid_page_rolls_back_and_wrong_identity_keeps_upload(tmp_path):
    s = store(tmp_path)
    s.set(6384, "actor", True)
    op = s.next_operation()
    with pytest.raises(ValueError):
        s.acknowledge(
            op, {"status": "applied", "record": {**remote(op), "person_id": 1}}
        )
    assert s.next_operation() == op
    other = store(tmp_path, "other")
    with pytest.raises(ValueError):
        other.apply_page({"protocol": 1, "changes": [remote(op)], "cursor": 2})
    assert other.cursor() == 0
    assert not other.keys()
    with pytest.raises(ValueError):
        validate({**op, "person_id": 0})


def test_guest_ui_csrf_and_cached_person_offline(app, client):
    mock_tmdb(app)
    assert client.get("/catalog_movie/603").status_code == 200
    response = post(
        client,
        "/people/actor/6384/favorite",
        favorite="1",
        name="Keanu Reeves",
        portrait_url="https://bad.invalid/photo.png",
    )
    assert response.status_code == 200
    assert (
        client.post("/people/actor/6384/favorite", data={"favorite": "0"}).status_code
        == 400
    )
    html = client.get("/people/favorites").get_data(as_text=True)
    assert "Keanu Reeves" in html and 'aria-pressed="true"' in html
    assert "bad.invalid" not in html
    assert client.get("/explore/person/6384").status_code == 200

    def offline(*a, **k):
        raise __import__("tmdb_client").TMDBError("Offline")

    app.extensions["tmdb"].get = offline
    assert client.get("/explore/person/6384").status_code == 200


class PeopleCloud(FakeCloud):
    def __init__(self):
        super().__init__()
        self.people = {}
        self.people_revisions = {}
        self.people_receipts = {}

    def push_person_favorite(self, token, op):
        self.health()
        owner = token[7:]
        receipt = (owner, op["operation_id"])
        if receipt in self.people_receipts:
            return deepcopy(self.people_receipts[receipt])
        key = (owner, op["role"], op["person_id"])
        old = self.people.get(key)
        if not old or op["edited_at"] > old["edited_at"]:
            rev = self.people_revisions.get(owner, 0) + 1
            self.people_revisions[owner] = rev
            self.people[key] = remote(op, rev)
        reply = {"status": "applied", "record": deepcopy(self.people[key])}
        self.people_receipts[receipt] = reply
        return deepcopy(reply)

    def pull_person_favorites(self, token, cursor):
        self.health()
        owner = token[7:]
        rows = sorted(
            [
                deepcopy(r)
                for (u, _, _), r in self.people.items()
                if u == owner and r["revision"] > cursor
            ],
            key=lambda r: r["revision"],
        )[:100]
        return {
            "protocol": 1,
            "changes": rows,
            "cursor": rows[-1]["revision"] if rows else cursor,
        }


def test_background_sync_two_devices_and_two_owners(tmp_path):
    fake = PeopleCloud()
    apps = []
    for n in range(2):
        folder = tmp_path / str(n)
        apps.append(
            create_app(
                {
                    "TESTING": True,
                    "DATA_DIR": str(folder),
                    "DATABASE": str(folder / "guest.db"),
                    "SECRET_KEY": "test",
                    "CLOUD_CLIENT": fake,
                    "CLOUD_SESSION_STORE": MemorySessions(),
                    "CLOUD_ACCOUNTS_READY": True,
                    "UI_LANGUAGE_DETECTOR": lambda: "en",
                }
            )
        )
        mock_tmdb(apps[-1])
        assert login(apps[-1].test_client()).status_code == 303
    one, two = [a.extensions["cloud"] for a in apps]
    one.active().people.set(6384, "actor", True)
    one.run_once()
    two.run_once()
    assert two.active().people.keys() == {"actor:6384"}
    two.active().people.set(6384, "actor", False)
    two.run_once()
    one.run_once()
    assert not one.active().people.keys()
    fake.offline = True
    one.active().people.set(1, "director", True)
    one.run_once()
    assert one.active().people.pending() == 1
    fake.offline = False
    one.states[A]["retry_at"] = 0
    one.run_once()
    two.run_once()
    assert two.active().people.keys() == {"director:1"}
    assert login(apps[1].test_client(), "b@example.test").status_code == 303
    two.run_once()
    assert two.active().owner == B and not two.active().people.keys()
    for a in apps:
        a.extensions["cloud"].close()
