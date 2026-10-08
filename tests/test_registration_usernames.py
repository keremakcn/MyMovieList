"""Registration claims are verified, moderated, owner-bound and immutable."""

import io
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError

import pytest
from test_app import post
from test_cloud_sync import A, B, StubOpener, login
from test_cloud_sync import account_app as make_account_app

from account_username import normalize_username
from cloud_client import CloudError, SupabaseClient
from name_policy import name_allowed


@pytest.fixture
def account_app(tmp_path):
    yield from make_account_app.__wrapped__(tmp_path)


def verified(client):
    assert post(client, "/account/signup", email="new@example.test").status_code == 303
    response = post(client, "/account/verify", code="123456")
    assert response.status_code == 303 and response.location.endswith("flow=username")


@pytest.mark.parametrize(
    "name",
    [
        "hitler",
        "H1TL3R",
        "h_i_t_l_e_r",
        "user_hitler88",
        "orospu",
        "s1kt1r",
        "yarrak",
        "amcık",
        "götveren",
        "nazi",
        "nazi88",
        "na_zi",
        "fuck_you",
        "shit123",
        "faggot",
        "ＦＵＣＫ",
        "HİTLER",
        "hítler",
    ],
)
def test_disallowed_identity_names(name):
    assert not name_allowed(name)


@pytest.mark.parametrize(
    "name",
    [
        "Nazim",
        "Nazım",
        "Nazife",
        "Scunthorpe",
        "Nigel",
        "Nigeria",
        "Kerem",
        "ClassicFilmFan",
        "CharlieChaplin",
        "Deniz_34",
        "Su Şirin",
        "",
    ],
)
def test_legitimate_names_are_not_matched_by_short_substrings(name):
    assert name_allowed(name)


def test_write_policy_does_not_discard_existing_username_reads():
    assert normalize_username("hitler") == "hitler"
    with pytest.raises(ValueError, match="not allowed"):
        normalize_username("hitler", writing=True)


def test_no_username_request_before_email_verification_or_through_recovery(account_app):
    app, fake, _ = account_app
    client = app.test_client()
    assert (
        post(client, "/account/register-username", username="new_user").status_code
        == 422
    )
    assert not fake.usernames
    assert post(client, "/account/recover", email="a@example.test").status_code == 303
    assert post(client, "/account/verify-reset", code="123456").status_code == 303
    assert (
        post(client, "/account/register-username", username="new_user").status_code
        == 422
    )
    assert not fake.usernames


def test_moderation_and_taken_name_preserve_registration_until_a_valid_claim(
    account_app,
):
    app, fake, vault = account_app
    fake.usernames[A] = "taken_user"
    client = app.test_client()
    verified(client)
    for name in ("h1tl3r", "taken_user", "admin"):
        response = post(client, "/account/register-username", username=name)
        assert response.status_code == 422 and 'name="username"' in response.get_data(
            as_text=True
        )
        assert B not in fake.usernames and vault.load() is None
    assert (
        post(client, "/account/register-username", username="New_User").status_code
        == 303
    )
    assert fake.usernames[B] == "new_user"
    assert (
        post(client, "/account/register-username", username="another_name").status_code
        == 422
    )
    assert (
        post(
            client,
            "/account/create-password",
            new_password="new-password",
            confirm_password="new-password",
        ).status_code
        == 303
    )
    assert app.extensions["cloud"].status()["username"]["username"] == "new_user"
    assert not app.extensions["cloud"].guest.query(
        "SELECT value FROM settings WHERE key='account_username'"
    )
    html = client.get("/account?flow=edit-profile").get_data(as_text=True)
    assert 'id="chosen-username"' in html and 'name="username"' not in html
    assert post(client, "/account/username", username="changed_name").status_code == 422
    assert fake.usernames[B] == "new_user"


def test_interrupted_claim_retry_preserves_first_username(account_app):
    app, fake, vault = account_app
    client = app.test_client()
    verified(client)
    original = fake.claim_username

    def lost_response(token, name):
        original(token, name)
        raise CloudError("Lost connection.", "offline")

    fake.claim_username = lost_response
    assert (
        post(client, "/account/register-username", username="first_name").status_code
        == 422
    )
    assert fake.usernames[B] == "first_name" and vault.load() is None
    fake.claim_username = original
    assert (
        post(client, "/account/register-username", username="other_name").status_code
        == 303
    )
    assert fake.usernames[B] == "first_name"
    html = client.get("/account?flow=password").get_data(as_text=True)
    assert "Your username is first_name" in html


def test_missing_policy_setup_stops_before_sending_email(account_app):
    app, fake, _ = account_app

    def missing():
        raise CloudError(
            "Usernames are being prepared. Please try again later.", "setup"
        )

    fake.username_health = missing
    assert (
        post(app.test_client(), "/account/signup", email="new@example.test").status_code
        == 422
    )
    assert not any(call[0] == "begin_signup" for call in fake.calls)


def test_profile_name_rejection_leaves_personal_notes_untouched(account_app):
    from test_cloud_sync import custom

    app, _fake, _ = account_app
    client = app.test_client()
    login(client)
    db = app.extensions["cloud"].active().db
    movie = custom(db, "hitler, fuck: a private movie review")
    before = app.extensions["cloud"].active().profile.snapshot()
    assert (
        post(
            client, "/account/profile", display_name="H1TL3R", avatar_id="cat-luna"
        ).status_code
        == 422
    )
    assert app.extensions["cloud"].active().profile.snapshot() == before
    assert db.movie(movie)["note"] == "hitler, fuck: a private movie review"
    assert (
        post(
            client, "/account/profile", display_name="Nazım", avatar_id="cat-luna"
        ).status_code
        == 303
    )


def test_adapter_checks_protocol_and_never_sends_disallowed_claim(monkeypatch):
    client = SupabaseClient("https://project.supabase.co", "sb_publishable_public")
    calls = []
    monkeypatch.setattr(
        client,
        "request",
        lambda *args, **kw: (
            calls.append(args) or {"service": "mymovielist-usernames", "protocol": 2}
        ),
    )
    client.username_health()
    assert calls[0][0] == "/rest/v1/rpc/mml_username_protocol"
    with pytest.raises(ValueError):
        client.claim_username("synthetic", "h1tl3r")
    assert len(calls) == 1


def test_server_name_policy_error_is_clear_and_redacted():
    error = HTTPError(
        "https://project.supabase.co",
        400,
        "Bad request",
        {},
        io.BytesIO(json.dumps({"code": "22023", "message": "PRIVATE INPUT"}).encode()),
    )
    client = SupabaseClient(
        "https://project.supabase.co", "sb_publishable_public", StubOpener(error=error)
    )
    with pytest.raises(CloudError) as raised:
        client.claim_username("synthetic", "future_policy_block")
    assert raised.value.kind == "validation"
    assert str(raised.value) == "This name is not allowed. Choose another one."


def test_double_registration_claim_is_serialized_and_cannot_rename(account_app):
    app, fake, _ = account_app
    client = app.test_client()
    verified(client)
    client.get("/account?flow=username")
    with client.session_transaction() as session:
        csrf = session["csrf_token"]
    other = app.test_client()
    other.set_cookie("session", client.get_cookie("session").value)
    entered, release = threading.Event(), threading.Event()
    original = fake.claim_username
    claims = []

    def slow(token, name):
        claims.append(name)
        entered.set()
        assert release.wait(3)
        return original(token, name)

    fake.claim_username = slow
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(
            client.post,
            "/account/register-username",
            data={"csrf_token": csrf, "username": "first_name"},
        )
        assert entered.wait(3)
        second = pool.submit(
            other.post,
            "/account/register-username",
            data={"csrf_token": csrf, "username": "other_name"},
        )
        release.set()
        assert first.result(timeout=5).status_code == 303
        assert second.result(timeout=5).status_code == 422
    assert claims == ["first_name"] and fake.usernames[B] == "first_name"
