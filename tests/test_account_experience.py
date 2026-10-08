"""Auth step boundaries, automatic sync and portable avatar/profile behavior."""

import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from test_app import mock_tmdb, post
from test_cloud_sync import A, B, MemorySessions, custom, login
from test_cloud_sync import account_app as make_account_app

from account_profile import AVATARS, remote_profile
from app import create_app
from auth_flows import AuthFlows
from cloud_client import SupabaseClient


@pytest.fixture
def account_app(tmp_path):
    yield from make_account_app.__wrapped__(tmp_path)


def registration(client):
    assert post(client, "/account/signup", email="new@example.test").status_code == 303
    assert post(client, "/account/verify", code="123456").status_code == 303
    assert (
        post(client, "/account/register-username", username="new_member").status_code
        == 303
    )


def recovery(client):
    assert post(client, "/account/recover", email="a@example.test").status_code == 303
    assert post(client, "/account/verify-reset", code="123456").status_code == 303


def test_registration_has_one_purpose_per_screen_and_no_password_before_verified(
    account_app,
):
    app, fake, vault = account_app
    client = app.test_client()
    html = client.get("/account?flow=signup").get_data(as_text=True)
    assert 'name="email"' in html and 'type="password"' not in html
    assert (
        post(
            client,
            "/account/signup",
            email="new@example.test",
            password="ignored-secret",
        ).status_code
        == 303
    )
    html = client.get("/account?flow=verify").get_data(as_text=True)
    assert 'name="code"' in html and 'type="password"' not in html
    assert post(client, "/account/verify", code="000000").status_code == 422
    assert (
        post(
            client,
            "/account/create-password",
            new_password="new-password",
            confirm_password="new-password",
        ).status_code
        == 422
    )
    assert not any(call[0] == "password" for call in fake.calls)
    assert (
        post(
            client, "/account/verify", code="123456", email="a@example.test"
        ).status_code
        == 303
    )
    html = client.get("/account?flow=username").get_data(as_text=True)
    assert 'name="username"' in html and 'type="password"' not in html
    assert vault.load() is None
    assert (
        post(
            client,
            "/account/create-password",
            new_password="new-password",
            confirm_password="new-password",
        ).status_code
        == 422
    )
    assert not any(call[0] == "password" for call in fake.calls)
    assert (
        post(client, "/account/register-username", username="new_member").status_code
        == 303
    )
    html = client.get("/account?flow=password").get_data(as_text=True)
    assert (
        'name="new_password"' in html
        and 'name="code"' not in html
        and 'name="email"' not in html
    )
    assert vault.load() is None
    assert (
        post(
            client,
            "/account/create-password",
            new_password="new-password",
            confirm_password="new-password",
        ).status_code
        == 303
    )
    assert vault.load()["user_id"] == B
    assert app.extensions["cloud"].enabled(app.extensions["cloud"].active())


def test_registration_never_replaces_existing_password(account_app):
    app, fake, vault = account_app
    client = app.test_client()
    assert post(client, "/account/signup", email="a@example.test").status_code == 303
    response = post(client, "/account/verify", code="123456")
    assert response.location.endswith("flow=signin")
    assert vault.load() is None
    assert (
        post(
            client,
            "/account/create-password",
            new_password="not-allowed",
            confirm_password="not-allowed",
        ).status_code
        == 422
    )
    assert not any(call[0] == "password" for call in fake.calls)


def test_recovery_session_stays_server_side_and_cannot_be_reused(account_app):
    app, fake, vault = account_app
    client = app.test_client()
    assert post(client, "/account/recover", email="a@example.test").status_code == 303
    html = client.get("/account?flow=reset-code").get_data(as_text=True)
    assert 'name="code"' in html and 'type="password"' not in html
    assert (
        post(
            client, "/account/verify-reset", code="123456", email="b@example.test"
        ).status_code
        == 303
    )
    html = client.get("/account?flow=reset").get_data(as_text=True)
    assert 'name="new_password"' in html and 'name="code"' not in html
    with client.session_transaction() as session:
        encoded = json.dumps(dict(session))
        assert "ACCESS-" not in encoded and "REFRESH-" not in encoded
        assert "credentials" not in encoded
    assert vault.load() is None
    assert (
        post(
            client,
            "/account/reset",
            new_password="new-password",
            confirm_password="new-password",
        ).status_code
        == 303
    )
    assert ("password", A) in fake.calls and ("password", B) not in fake.calls
    assert (
        post(
            client,
            "/account/reset",
            new_password="other-password",
            confirm_password="other-password",
        ).status_code
        == 422
    )
    assert sum(call[0] == "password" for call in fake.calls) == 1


@pytest.mark.parametrize("endpoint", ["/account/reset", "/account/create-password"])
def test_direct_password_requests_cannot_skip_verification(account_app, endpoint):
    app, fake, _ = account_app
    client = app.test_client()
    response = post(
        client,
        endpoint,
        email="a@example.test",
        code="123456",
        new_password="new-password",
        confirm_password="new-password",
    )
    assert response.status_code == 422
    assert not any(call[0] in ("password", "verify") for call in fake.calls)


def test_expiration_new_browser_and_account_switch_invalidate_steps(account_app):
    app, fake, _ = account_app
    client = app.test_client()
    registration(client)
    other = app.test_client()
    assert (
        post(
            other,
            "/account/create-password",
            new_password="new-password",
            confirm_password="new-password",
        ).status_code
        == 422
    )
    clock = app.extensions["auth_flows"].clock
    app.extensions["auth_flows"].clock = lambda: clock() + 601
    assert (
        post(
            client,
            "/account/create-password",
            new_password="new-password",
            confirm_password="new-password",
        ).status_code
        == 422
    )
    app.extensions["auth_flows"].clock = clock
    assert login(other).status_code == 303
    assert (
        post(
            client,
            "/account/create-password",
            new_password="new-password",
            confirm_password="new-password",
        ).status_code
        == 422
    )
    assert not any(call[0] == "password" for call in fake.calls)


def test_resend_is_limited_and_verifies_same_address(account_app):
    app, fake, _ = account_app
    client = app.test_client()
    assert post(client, "/account/signup", email="new@example.test").status_code == 303
    assert post(client, "/account/resend").status_code == 422
    assert post(client, "/account/signup", email="new@example.test").status_code == 422
    flows = app.extensions["auth_flows"]
    clock = flows.clock
    flows.clock = lambda: clock() + 61
    assert post(client, "/account/resend", email="b@example.test").status_code == 303
    assert [c for c in fake.calls if c[0] == "begin_signup"] == [
        ("begin_signup", "new@example.test")
    ] * 2


def test_verified_recovery_cannot_be_used_as_signup(account_app):
    app, fake, _ = account_app
    client = app.test_client()
    recovery(client)
    assert (
        post(
            client,
            "/account/create-password",
            new_password="new-password",
            confirm_password="new-password",
        ).status_code
        == 422
    )
    assert not any(call[0] == "password" for call in fake.calls)


def test_double_password_submission_updates_only_once(account_app):
    app, fake, _ = account_app
    client = app.test_client()
    recovery(client)
    client.get("/account?flow=reset")
    with client.session_transaction() as session:
        csrf = session["csrf_token"]
    other = app.test_client()
    other.set_cookie("session", client.get_cookie("session").value)
    entered, release = threading.Event(), threading.Event()
    original = fake.change_password

    def slow(*args):
        entered.set()
        assert release.wait(3)
        return original(*args)

    fake.change_password = slow
    data = {
        "csrf_token": csrf,
        "new_password": "new-password",
        "confirm_password": "new-password",
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(client.post, "/account/reset", data=data)
        assert entered.wait(3)
        second = pool.submit(other.post, "/account/reset", data=data)
        release.set()
        assert first.result(timeout=5).status_code == 303
        assert second.result(timeout=5).status_code in (400, 422)
    assert sum(call[0] == "password" for call in fake.calls) == 1


def test_profile_queued_offline_survives_restart_and_reaches_another_device(
    account_app, tmp_path
):
    app, fake, vault = account_app
    client = app.test_client()
    login(client)
    fake.offline = True
    assert (
        post(
            client, "/account/profile", display_name="Deniz", avatar_id="cat-mint"
        ).status_code
        == 303
    )
    cloud = app.extensions["cloud"]
    cloud.run_once()
    assert cloud.status()["pending"] == 1
    assert cloud.active().profile.snapshot()["profile"] == {
        "display_name": "Deniz",
        "avatar_id": "cat-mint",
    }
    same = create_app(dict(app.config, CLOUD_SESSION_STORE=vault))
    try:
        assert same.extensions["cloud"].active().profile.snapshot()["dirty"]
    finally:
        same.extensions["cloud"].close()
    fake.offline = False
    cloud.states[A]["retry_at"] = 0
    cloud.run_once()
    assert cloud.status()["pending"] == 0
    device = tmp_path / "other-device"
    other = create_app(
        {
            "TESTING": True,
            "DATA_DIR": str(device),
            "DATABASE": str(device / "guest.db"),
            "SECRET_KEY": "synthetic",
            "CLOUD_CLIENT": fake,
            "CLOUD_SESSION_STORE": MemorySessions(),
            "CLOUD_ACCOUNTS_READY": True,
            "UI_LANGUAGE_DETECTOR": lambda: "en",
        }
    )
    try:
        mock_tmdb(other)
        login(other.test_client())
        assert other.extensions["cloud"].active().profile.snapshot()["profile"] == {
            "display_name": "Deniz",
            "avatar_id": "cat-mint",
        }
    finally:
        other.extensions["cloud"].close()


@pytest.mark.parametrize(
    "name,avatar",
    [("x" * 41, "cat-luna"), ("valid", "../outside"), ("bad\x00name", "cat-luna")],
)
def test_invalid_profile_is_rejected_without_changing_it(account_app, name, avatar):
    app, _fake, _ = account_app
    client = app.test_client()
    login(client)
    before = app.extensions["cloud"].active().profile.snapshot()
    assert (
        post(
            client, "/account/profile", display_name=name, avatar_id=avatar
        ).status_code
        == 422
    )
    assert app.extensions["cloud"].active().profile.snapshot() == before


def test_profile_owner_separation_and_html_escaping(account_app):
    app, fake, _ = account_app
    client = app.test_client()
    login(client)
    assert (
        post(
            client,
            "/account/profile",
            display_name="<script>alert(1)</script>",
            avatar_id="cat-coral",
        ).status_code
        == 303
    )
    html = client.get("/account").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    app.extensions["cloud"].run_once()
    login(client, "b@example.test")
    assert app.extensions["cloud"].status()["profile"]["display_name"] == ""
    assert fake.profiles[A]["avatar_id"] == "cat-coral"
    assert post(client, "/account/signout").status_code == 303
    assert (
        post(
            client, "/account/profile", display_name="guest", avatar_id="cat-luna"
        ).status_code
        == 403
    )


def test_profile_ack_does_not_erase_a_newer_edit(account_app):
    app, _fake, _ = account_app
    login(app.test_client())
    store = app.extensions["cloud"].active().profile
    store.save({"display_name": "First", "avatar_id": "cat-luna"})
    frozen = store.snapshot()
    store.save({"display_name": "Newer", "avatar_id": "cat-sky"})
    assert not store.receive(frozen["profile"], frozen["generation"])
    assert (
        store.snapshot()["dirty"]
        and store.snapshot()["profile"]["display_name"] == "Newer"
    )


def test_signin_automatically_syncs_account_but_does_not_copy_guest(account_app):
    app, fake, _ = account_app
    custom(app.extensions["cloud"].guest, "private guest note")
    client = app.test_client()
    login(client)
    cloud = app.extensions["cloud"]
    assert cloud.enabled(cloud.active()) and not cloud.active().db.query(
        "SELECT * FROM movies"
    )
    mid = custom(cloud.active().db)
    cloud.run_once()
    assert cloud.active().store.pending() == 0 and len(fake.records) == 1
    assert client.get("/api/account/status").json["state"] == "current"
    assert b"private guest note" not in client.get("/account/export").data
    assert post(client, "/account/sync-settings", enabled="0").status_code == 303
    cloud.active().db.update_personal(mid, {"note": "while paused"})
    cloud.run_once()
    assert cloud.status()["state"] == "paused" and cloud.active().store.pending() == 1
    post(client, "/account/signout")
    login(client)
    assert cloud.status()["state"] == "paused"


def test_backups_in_settings_and_profile_access_in_header(account_app):
    app, _, _ = account_app
    client = app.test_client()
    assert b"topbar-auth" in client.get("/").data
    assert b'id="library-file"' in client.get("/settings").data
    assert b'id="library-file"' not in client.get("/account").data
    login(client)
    assert b"account-menu" in client.get("/").data
    assert b"Sync now" not in client.get("/account").data
    assert b"Enable cloud sync" not in client.get("/account").data


def profile_counts(html):
    return {
        key: int(value)
        for key, value in re.findall(
            r'data-profile-stat="([^"]+)"[^>]*>.*?<strong>(\d+)</strong>',
            html,
            re.DOTALL,
        )
    }


def test_profile_summary_respects_owner_deletions_and_undo(account_app):
    app, _, _ = account_app
    cloud = app.extensions["cloud"]
    guest = custom(cloud.guest)
    cloud.guest.update_personal(guest, {"status": "Watched", "favorite": 1})
    client = app.test_client()
    login(client)
    db = cloud.active().db
    first, second, waiting, removed = [custom(db) for _ in range(4)]
    db.update_personal(first, {"status": "Watched", "favorite": 1, "rating": 9})
    db.update_personal(second, {"status": "Watched", "favorite": 0, "rating": 8})
    db.update_personal(waiting, {"status": "Watchlist", "favorite": 1, "rating": None})
    db.update_personal(removed, {"status": "Watched", "favorite": 1, "rating": 10})
    marker = db.remove(removed)
    expected = {"all": 3, "Watched": 2, "favorite": 2, "Watchlist": 1}
    assert (
        profile_counts(client.get("/account?view=personal").get_data(as_text=True))
        == expected
    )
    assert db.library_stats()["average"] == 8.5
    assert db.restore(removed, marker)
    assert profile_counts(
        client.get("/account?view=personal").get_data(as_text=True)
    ) == {
        "all": 4,
        "Watched": 3,
        "favorite": 3,
        "Watchlist": 1,
    }
    login(client, "b@example.test")
    assert profile_counts(
        client.get("/account?view=personal").get_data(as_text=True)
    ) == {
        "all": 0,
        "Watched": 0,
        "favorite": 0,
        "Watchlist": 0,
    }


def test_profile_sidebar_active_state_and_summary_links(account_app):
    app, _, _ = account_app
    client = app.test_client()
    login(client)
    html = client.get("/account?view=personal").get_data(as_text=True)
    nav = html.split('<nav class="app-nav"', 1)[1].split("</nav>", 1)[0]
    assert 'class="profile-nav"' in nav
    assert nav.count('aria-current="page"') == 1
    assert re.search(r'class="profile-nav"\s+aria-current="page"', nav)
    for status in ("all", "Watched", "favorite", "Watchlist"):
        assert f'href="/?status={status}"' in html
        assert client.get(f"/?status={status}").status_code == 200
    settings = client.get("/settings").get_data(as_text=True)
    nav = settings.split('<nav class="app-nav"', 1)[1].split("</nav>", 1)[0]
    assert nav.count('aria-current="page"') == 1
    assert not re.search(r'class="profile-nav"\s+aria-current="page"', nav)


def test_avatar_pack_and_unknown_remote_avatar_fallback():
    folder = Path(__file__).parents[1] / "static" / "avatars"
    assert len(AVATARS) == 16
    assert all((folder / (key + ".svg")).is_file() for key, _ in AVATARS)
    assert sum(p.stat().st_size for p in folder.glob("*.svg")) < 100_000
    assert remote_profile(
        {"mml_profile": {"display_name": "Future", "avatar_id": "future-avatar"}}
    ) == {"display_name": "Future", "avatar_id": "cat-luna"}
    assert remote_profile({"mml_profile": {"avatar_id": []}})["avatar_id"] == "cat-luna"


def test_supabase_adapter_uses_otp_only_for_registration_and_validated_metadata(
    monkeypatch,
):
    client = SupabaseClient("https://project.supabase.co", "sb_publishable_public")
    calls = []
    monkeypatch.setattr(
        client, "request", lambda *args, **kwargs: calls.append((args, kwargs)) or {}
    )
    client.begin_signup("new@example.test")
    assert calls[-1][0][0] == "/auth/v1/otp"
    assert calls[-1][0][1] == {
        "email": "new@example.test",
        "create_user": True,
        "data": {"mml_registration": "pending-v1"},
    }
    client.update_profile(
        "token", {"display_name": "Name", "avatar_id": "cat-mint", "role": "admin"}
    )
    assert calls[-1][0][1] == {
        "data": {"mml_profile": {"display_name": "Name", "avatar_id": "cat-mint"}}
    }


def test_flow_capacity_expiry_and_scope():
    now = [1]
    steps = AuthFlows(clock=lambda: now[0], capacity=1)
    key = steps.start("signup", "one@example.test", "scope")
    assert steps.view(key, "other") is None
    with pytest.raises(ValueError):
        steps.start("signup", "two@example.test", "scope")
    now[0] = 1802
    assert steps.view(key, "scope") is None
    assert steps.start("signup", "two@example.test", "scope")
