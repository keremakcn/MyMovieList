"""Username ownership is separate from private profile metadata and consent."""

from copy import deepcopy

import pytest
from test_app import mock_tmdb, post
from test_cloud_sync import A, B, MemorySessions, login
from test_public_profiles import SharingCloud, prepare, publish

from account_username import UsernameStore, normalize_username, validate_username_status
from app import create_app
from cloud_client import CloudError, SupabaseClient
from profile_sharing import validate_public_profile


class UsernameCloud(SharingCloud):
    def __init__(self):
        super().__init__()
        self.usernames = {}
        self.missing_usernames = False

    def username_status(self, token):
        self.health()
        if self.missing_usernames:
            raise CloudError("Missing username setup.", "setup")
        return {"username": self.usernames.get(token[7:])}

    def claim_username(self, token, username):
        current = self.username_status(token)["username"]
        owner = token[7:]
        if current:
            status = "claimed" if current == username else "locked"
        elif username in self.usernames.values():
            status = "taken"
        else:
            self.usernames[owner] = username
            current, status = username, "claimed"
        return {"status": status, "username": current}

    def public_profile_by_username(self, username):
        owner = next(
            (key for key, name in self.usernames.items() if name == username), None
        )
        share = self.sharing.get(owner, {}).get("share_id")
        public = self.public_profile(share) if share else {"found": False}
        return dict(public, username=username) if public["found"] else public


@pytest.fixture
def username_app(tmp_path):
    fake = UsernameCloud()
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


@pytest.mark.parametrize(
    "value",
    [
        "ab",
        "1name",
        "has space",
        "a" * 25,
        "şirin",
        "Kerem",
        "../admin",
        "a\nb",
        "ADMIN",
        "api",
        "support",
        None,
        [],
    ],
)
def test_invalid_and_reserved_names(value):
    with pytest.raises(ValueError):
        normalize_username(value)


def test_normalization_and_strict_remote_response():
    assert normalize_username("  BiStr_Kerem  ") == "bistr_kerem"
    assert validate_username_status({"username": None}) == {"username": None}
    for value in (
        {"username": "UPPER"},
        {"username": "valid", "owner": A},
        {"username": 4},
    ):
        with pytest.raises(ValueError):
            validate_username_status(value)


def test_duplicate_display_names_allowed_but_username_cannot_be_taken_twice(
    username_app,
):
    app, fake = username_app
    client = app.test_client()
    login(client)
    cloud = app.extensions["cloud"]
    assert post(client, "/account/username", username="BiStrKerem").status_code == 303
    assert (
        post(
            client, "/account/profile", display_name="Kerem", avatar_id="cat-luna"
        ).status_code
        == 303
    )
    assert cloud.status()["username"]["url"] == "https://myshelf.cloud/u/bistrkerem"
    assert not cloud.status()["sharing"]["is_public"]
    cloud.run_once()
    assert fake.profiles[A]["display_name"] == "Kerem"
    assert "username" not in fake.profiles[A]  # Auth metadata cannot reserve a name.
    login(client, "b@example.test")
    assert post(client, "/account/username", username="BISTRKEREM").status_code == 422
    assert (
        post(
            client, "/account/profile", display_name="Kerem", avatar_id="cat-lilac"
        ).status_code
        == 303
    )
    assert post(client, "/account/username", username="other_kerem").status_code == 303
    cloud.run_once()
    assert fake.profiles[B]["display_name"] == "Kerem"
    assert fake.usernames == {A: "bistrkerem", B: "other_kerem"}


def test_claim_is_idempotent_stable_and_never_publishes(username_app):
    app, fake = username_app
    client = app.test_client()
    assert post(client, "/account/username", username="deniz").status_code == 403
    login(client)
    assert post(client, "/account/username", username="deniz").status_code == 303
    assert post(client, "/account/username", username="DENIZ").status_code == 303
    assert post(client, "/account/username", username="new_name").status_code == 422
    assert app.extensions["cloud"].status()["username"]["username"] == "deniz"
    assert not fake.sharing
    page = client.get("/account?flow=edit-profile").get_data(as_text=True)
    assert "chosen-username" in page and "Your display name" in page
    assert 'action="/account/username"' not in page


def test_offline_claim_never_claims_success_or_changes_display_name(username_app):
    app, fake = username_app
    client = app.test_client()
    login(client)
    original = deepcopy(app.extensions["cloud"].status()["profile"])
    fake.offline = True
    response = post(
        client, "/account/username", username="deniz", display_name="Lost name"
    )
    assert response.status_code == 503
    assert "Could not confirm your username" in response.get_data(as_text=True)
    assert not fake.usernames
    assert app.extensions["cloud"].status()["profile"] == original


def test_missing_migration_does_not_break_private_profile_or_library_sync(username_app):
    app, fake = username_app
    client, cloud, library, _ = prepare(app)
    fake.missing_usernames = True
    library.username.next_attempt = 0
    cloud.run_once()
    assert cloud.status()["username"]["error"] == "setup"
    assert cloud.status()["state"] == "current"
    assert post(client, "/account/username", username="deniz").status_code == 503
    assert (
        post(
            client,
            "/account/profile",
            display_name="New display name",
            avatar_id="cat-luna",
        ).status_code
        == 303
    )


def test_username_read_on_other_device_and_while_sync_paused(username_app):
    app, fake = username_app
    client = app.test_client()
    login(client)
    cloud = app.extensions["cloud"]
    cloud.set_enabled(False)
    fake.usernames[A] = "already_chosen"
    cloud.run_once()
    assert cloud.status()["username"]["username"] == "already_chosen"
    assert cloud.status()["username"]["url"].endswith("/u/already_chosen")
    assert cloud.status()["state"] == "paused"


def test_named_public_visit_same_curated_projection_and_revocation(username_app):
    app, fake = username_app
    client, cloud, library, _ = prepare(app)
    assert post(client, "/account/username", username="deniz").status_code == 303
    assert app.test_client().get("/profiles/u/deniz").status_code == 404
    share = publish(client, cloud, library)
    assert cloud.status()["sharing"]["url"] == "https://myshelf.cloud/u/deniz"
    assert cloud.status()["sharing"]["visitor_path"] == "/profiles/u/deniz"
    cloud.sign_out()
    visitor = app.test_client()
    for path in ("/profiles/u/deniz", "/profiles/" + share):
        response = visitor.get(path)
        assert response.status_code == 200
        assert "Deniz" in response.get_data(as_text=True)
        assert "NEVER-PUBLIC-NOTE" not in response.get_data(as_text=True)
    assert fake.public_profile_by_username("deniz")["username"] == "deniz"
    fake.sharing[A]["is_public"] = False
    assert visitor.get("/profiles/u/deniz").status_code == 404
    assert visitor.get("/profiles/" + share).status_code == 404


def test_public_named_client_uses_fixed_anonymous_rpc():
    client = SupabaseClient("https://example.supabase.co", "sb_publishable_test")
    calls = []
    client.request = lambda path, body, **kw: (
        calls.append((path, body, kw)) or {"found": False}
    )
    assert client.public_profile_by_username("DeNiZ") == {"found": False}
    assert calls == [
        ("/rest/v1/rpc/mml_public_profile_by_username", {"p_username": "deniz"}, {})
    ]
    with pytest.raises(ValueError):
        validate_public_profile({"found": False, "username": "deniz"})


def test_changed_account_cannot_inherit_previous_username(username_app):
    app, _fake = username_app
    client = app.test_client()
    login(client)
    assert post(client, "/account/username", username="deniz").status_code == 303
    login(client, "b@example.test")
    cloud = app.extensions["cloud"]
    assert cloud.status()["username"]["username"] is None
    cloud.run_once()
    assert cloud.status()["username"]["username"] is None


def test_stale_null_status_or_error_cannot_erase_a_successful_claim(username_app):
    app, _fake = username_app
    client = app.test_client()
    login(client)
    library = app.extensions["cloud"].active()
    # Another store simulates a background read that was already in flight.
    background = UsernameStore(library.db, True)
    library.username.receive({"username": "deniz"})
    background.receive({"username": None})
    assert library.username.view()["username"] == "deniz"
    background.error("offline")
    assert library.username.view()["url"] == "https://myshelf.cloud/u/deniz"
    with pytest.raises(ValueError):
        background.receive({"username": "another_owner"})
    assert library.username.view()["username"] == "deniz"
