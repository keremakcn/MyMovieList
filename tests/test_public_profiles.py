"""Public projection, durable consent and stale-device privacy protection."""

from copy import deepcopy
from uuid import uuid4

import pytest
from test_app import mock_tmdb, post
from test_cloud_sync import A, B, FakeCloud, MemorySessions, custom, login

from app import create_app
from cloud_client import CloudError
from profile_sharing import SharingStore, validate_public_profile


class SharingCloud(FakeCloud):
    def __init__(self):
        super().__init__()
        self.sharing = {}
        self.receipt = {}
        self.sharing_setup_missing = False

    def sharing_status(self, token):
        self.health()
        if self.sharing_setup_missing:
            raise CloudError("Missing showcase setup.", "setup")
        return deepcopy(
            self.sharing.get(
                token[7:], {"share_id": None, "is_public": False, "revision": 0}
            )
        )

    def write_showcase(self, token, op):
        owner = token[7:]
        current = self.sharing_status(token)
        self.calls.append(("sharing", owner, op["action"]))
        if (owner, op["operation_id"]) in self.receipt:
            return deepcopy(self.receipt[owner, op["operation_id"]])
        if op["action"] != "unpublish" and (
            current["revision"] != op["expected_revision"]
            or op["action"] == "update"
            and not current["is_public"]
        ):
            return {"status": "conflict", "settings": current}
        if op["action"] != "unpublish":
            assert all(
                (owner, "tmdb:" + str(mid)) in self.records
                for mid in op["payload"]["tmdb_ids"]
            )
            self.sharing[owner + "-payload"] = deepcopy(op["payload"])
        current.update(
            share_id=current["share_id"] or str(uuid4()),
            is_public=op["action"] != "unpublish",
            revision=current["revision"] + 1,
        )
        self.sharing[owner] = current
        result = {"status": "applied", "settings": deepcopy(current)}
        self.receipt[owner, op["operation_id"]] = result
        return deepcopy(result)

    def public_profile(self, share_id):
        self.health()
        for owner in (A, B):
            row = self.sharing.get(owner, {})
            if row.get("share_id") != share_id or not row["is_public"]:
                continue
            payload = self.sharing[owner + "-payload"]
            films = []
            for mid in payload["tmdb_ids"]:
                data = self.records[owner, "tmdb:" + str(mid)]["data"]
                if data["deleted_at"] is not None:
                    continue
                film = {"tmdb_id": mid}
                if payload["show_ratings"] and data["rating"] is not None:
                    film["rating"] = data["rating"]
                films.append(film)
            return validate_public_profile(
                {
                    "found": True,
                    "share_id": share_id,
                    "display_name": payload["display_name"],
                    "avatar_id": payload["avatar_id"],
                    "films": films,
                }
            )
        return {"found": False}


@pytest.fixture
def sharing_app(tmp_path):
    fake = SharingCloud()
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "synthetic",
            "DATA_DIR": str(tmp_path),
            "DATABASE": str(tmp_path / "guest.db"),
            "UI_LANGUAGE_DETECTOR": lambda: "en",
            "BACKGROUND_METADATA": False,
            "CLOUD_ACCOUNTS_READY": True,
            "PUBLIC_PROFILES_READY": True,
            "CLOUD_CLIENT": fake,
            "CLOUD_SESSION_STORE": MemorySessions(),
        }
    )
    mock_tmdb(app)
    yield app, fake
    app.extensions["cloud"].close()


def prepare(app):
    client = app.test_client()
    login(client)
    cloud = app.extensions["cloud"]
    cloud.set_enabled(True)
    library = cloud.active()
    mid = library.db.add_tmdb(
        {
            "tmdb_id": 603,
            "title": "The Matrix",
            "status": "Watched",
            "rating": 9,
            "note": "NEVER-PUBLIC-NOTE",
            "favorite": 1,
        }
    )
    custom(library.db, "CUSTOM-PRIVATE-NOTE")
    library.profile.save(
        {
            "display_name": "Deniz",
            "avatar_id": "cat-lilac",
            "showcase": {
                "record_keys": ["tmdb:603"],
                "show_ratings": False,
                "show_stats": False,
            },
        }
    )
    cloud.run_once()
    return client, cloud, library, mid


def publish(client, cloud, library):
    assert (
        post(client, "/account/sharing", action="publish", consent="1").status_code
        == 303
    )
    assert library.sharing.view()["pending"] == "publish"
    assert not library.sharing.view()["is_public"]
    cloud.run_once()
    return library.sharing.view()["share_id"]


def test_explicit_consent_only_curated_projection_and_anonymous_visit(sharing_app):
    app, fake = sharing_app
    client, cloud, library, _ = prepare(app)
    assert post(client, "/account/sharing", action="publish").status_code == 422
    assert (
        post(client, "/account/sharing", action="delete", consent="1").status_code
        == 422
    )
    assert not fake.sharing
    share = publish(client, cloud, library)
    assert library.sharing.view()["is_public"]
    cloud.sign_out()
    page = app.test_client().get("/profiles/" + share)
    assert page.status_code == 200
    text = page.get_data(as_text=True)
    assert "The Matrix" in text and "Deniz" in text
    for secret in (
        "NEVER-PUBLIC-NOTE",
        "CUSTOM-PRIVATE-NOTE",
        "Private custom film",
        "a@example.test",
        "ACCESS-",
        "REFRESH-",
    ):
        assert secret not in text
    assert page.headers["Cache-Control"] == "no-store"
    assert "Add The Matrix to Want to Watch" in text
    assert not cloud.guest.query("SELECT * FROM movies")
    view = fake.public_profile(share)
    assert view["films"] == [{"tmdb_id": 603}] and "counts" not in view


def test_offline_revocation_durable_prioritized_when_paused(sharing_app):
    app, fake = sharing_app
    client, cloud, library, _ = prepare(app)
    share = publish(client, cloud, library)
    cloud.set_enabled(False)
    fake.offline = True
    assert post(client, "/account/sharing", action="unpublish").status_code == 303
    cloud.run_once()
    view = SharingStore(library.db, True).view()
    assert view["pending"] == "unpublish" and view["is_public"]
    assert "may remain visible until connected" in client.get("/account").get_data(
        as_text=True
    )
    fake.offline = False
    library.sharing.next_attempt = 0
    cloud.states[A] = {"retry_at": 10**20}
    cloud.run_once()
    assert (
        not library.sharing.view()["is_public"]
        and not library.sharing.view()["pending"]
    )
    assert fake.public_profile(share) == {"found": False}
    assert app.test_client().get("/profiles/" + share).status_code == 404


def test_remote_revocation_cannot_be_overwritten_by_stale_profile_save(sharing_app):
    app, fake = sharing_app
    client, cloud, library, _ = prepare(app)
    share = publish(client, cloud, library)
    remote = fake.sharing[A]
    fake.write_showcase(
        "ACCESS-" + A,
        {
            "operation_id": str(uuid4()),
            "expected_revision": remote["revision"],
            "action": "unpublish",
            "payload": {},
        },
    )
    library.profile.save({"display_name": "Local edited name"})
    cloud.run_once()
    assert not library.sharing.view()["is_public"]
    assert library.sharing.view()["error"] == "changed"
    assert fake.public_profile(share) == {"found": False}
    assert library.profile.snapshot()["profile"]["display_name"] == "Local edited name"


def test_private_profile_update_preserves_pending_publish_followup(sharing_app):
    app, fake = sharing_app
    client, cloud, library, _ = prepare(app)
    assert (
        post(client, "/account/sharing", action="publish", consent="1").status_code
        == 303
    )
    library.profile.save({"display_name": "Latest name"})
    cloud.run_once()
    assert library.sharing.view()["pending"] == "update"
    library.sharing.next_attempt = 0
    cloud.run_once()
    assert fake.sharing[A + "-payload"]["display_name"] == "Latest name"


def test_automatic_showcase_edits_keep_flags_order_and_never_publish_custom(
    sharing_app,
):
    app, fake = sharing_app
    client, cloud, library, _ = prepare(app)
    share = publish(client, cloud, library)
    row = library.db.query("SELECT record_key FROM movies WHERE tmdb_id IS NULL")[0]
    library.profile.save(
        {
            "showcase": {
                "record_keys": [row["record_key"], "tmdb:603"],
                "show_ratings": True,
                "show_stats": False,
            }
        }
    )
    cloud.run_once()
    payload = fake.sharing[A + "-payload"]
    assert payload["tmdb_ids"] == [603]
    assert fake.public_profile(share)["films"] == [{"tmdb_id": 603, "rating": 9}]


def test_missing_setup_never_interrupts_private_library_sync(sharing_app):
    app, fake = sharing_app
    fake.sharing_setup_missing = True
    client, _cloud, library, _mid = prepare(app)
    assert library.store.pending() == 0
    assert fake.records[A, "tmdb:603"]["data"]["note"] == "NEVER-PUBLIC-NOTE"
    assert (
        post(client, "/account/sharing", action="publish", consent="1").status_code
        == 503
    )
    assert b"Public profiles are being prepared" in client.get("/account").data


def test_public_visits_private_and_absent_match_and_errors_do_not_leak(sharing_app):
    app, fake = sharing_app
    client, cloud, library, _ = prepare(app)
    share = publish(client, cloud, library)
    fake.sharing[A]["is_public"] = False
    cloud.sign_out()
    visitor = app.test_client()
    private = visitor.get("/profiles/" + share)
    missing = visitor.get("/profiles/" + str(uuid4()))
    assert private.status_code == missing.status_code == 404
    assert "Deniz" not in private.get_data(as_text=True)
    fake.offline = True
    assert visitor.get("/profiles/" + share).status_code == 503
    assert post(visitor, "/account/sharing", action="unpublish").status_code == 403


@pytest.mark.parametrize(
    "value",
    [
        {"found": False, "note": "SECRET"},
        {"found": True},
        {
            "found": True,
            "share_id": A,
            "display_name": "x",
            "avatar_id": "cat-luna",
            "films": [],
            "email": "secret",
        },
        {
            "found": True,
            "share_id": A,
            "display_name": "x",
            "avatar_id": "cat-luna",
            "films": [{"tmdb_id": 603, "note": "SECRET"}],
        },
        {
            "found": True,
            "share_id": A,
            "display_name": "x",
            "avatar_id": "cat-luna",
            "films": [{"tmdb_id": True}],
        },
        {
            "found": True,
            "share_id": A,
            "display_name": "x",
            "avatar_id": [],
            "films": [],
        },
    ],
)
def test_public_projection_rejects_private_or_invalid_fields(value):
    with pytest.raises((ValueError, TypeError)):
        validate_public_profile(value)


def test_damaged_sharing_state_falls_back_without_crashing(sharing_app):
    app, _ = sharing_app
    client, _, library, _ = prepare(app)
    library.db.execute(
        "INSERT OR REPLACE INTO settings VALUES ('profile_sharing',?)",
        '{"operation":{"bad":true}}',
    )
    assert library.sharing.view()["pending"] is None
    assert client.get("/account").status_code == 200


def test_duplicate_publish_keeps_one_durable_operation(sharing_app):
    app, _fake = sharing_app
    client, cloud, library, _mid = prepare(app)
    assert (
        post(client, "/account/sharing", action="publish", consent="1").status_code
        == 303
    )
    first = library.sharing.snapshot()["operation"]
    assert (
        post(client, "/account/sharing", action="publish", consent="1").status_code
        == 303
    )
    assert library.sharing.snapshot()["operation"] == first
    cloud.run_once()
    assert library.sharing.view()["revision"] == 1


def test_paused_sync_still_checks_remote_privacy_without_publishing(sharing_app):
    app, fake = sharing_app
    client, cloud, library, _mid = prepare(app)
    share = publish(client, cloud, library)
    cloud.set_enabled(False)
    fake.sharing[A].update(is_public=False, revision=2)
    library.sharing.next_attempt = 0
    cloud.run_once()
    assert not library.sharing.view()["is_public"]
    assert fake.public_profile(share) == {"found": False}
    cloud.set_enabled(True)
    assert (
        post(client, "/account/sharing", action="publish", consent="1").status_code
        == 303
    )
    cloud.set_enabled(False)
    cloud.run_once()
    assert library.sharing.view()["pending"] == "publish"
    assert not fake.sharing[A]["is_public"]
