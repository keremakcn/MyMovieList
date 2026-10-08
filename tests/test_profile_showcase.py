"""Private film shelves, offline presentation and separate owner controls."""

import json
import re

import pytest
from test_app import MOVIE, post
from test_cloud_sync import A, custom, login
from test_cloud_sync import account_app as make_account_app


@pytest.fixture
def account_app(tmp_path):
    yield from make_account_app.__wrapped__(tmp_path)


def shelf_ids(html, name):
    shelf = html.split(f'data-profile-shelf="{name}"', 1)[1].split("</section>", 1)[0]
    return [int(value) for value in re.findall(r'data-profile-film="(\d+)"', shelf)]


def test_shelves_are_bounded_private_local_and_exclude_removed_movies(account_app):
    app, fake, _ = account_app
    cloud = app.extensions["cloud"]
    guest = custom(cloud.guest, "GUEST-NOTE-MUST-STAY-PRIVATE")
    cloud.guest.execute("UPDATE movies SET title='Guest-only film' WHERE id=?", guest)
    client = app.test_client()
    login(client)
    db = cloud.active().db
    ids = [custom(db, "PRIVATE-NOTE-MUST-STAY-PRIVATE") for _ in range(9)]
    removed = ids[-1]
    marker = db.remove(removed)
    fake.offline = True

    def no_discovery(*args, **kwargs):
        pytest.fail("Profile navigation must not request TMDB")

    app.extensions["tmdb"].get = no_discovery
    calls = len(fake.calls)
    html = client.get("/account?view=personal").get_data(as_text=True)
    assert len(fake.calls) == calls
    assert shelf_ids(html, "favorites") == list(reversed(ids[-7:-1]))
    assert shelf_ids(html, "recent") == list(reversed(ids[-7:-1]))
    assert "PRIVATE-NOTE-MUST-STAY-PRIVATE" not in html
    assert "GUEST-NOTE-MUST-STAY-PRIVATE" not in html
    assert "Guest-only film" not in html
    assert 'name="avatar_id"' not in html and 'name="display_name"' not in html
    assert 'action="/account/sync-settings"' not in html
    assert db.restore(removed, marker)
    assert (
        shelf_ids(
            client.get("/account?view=personal").get_data(as_text=True), "favorites"
        )[0]
        == removed
    )
    fake.offline = False
    login(client, "b@example.test")
    html = client.get("/account?view=personal").get_data(as_text=True)
    assert shelf_ids(html, "favorites") == shelf_ids(html, "recent") == []


def test_recent_watches_use_dates_not_last_edit_and_fall_back_to_additions(account_app):
    app, _, _ = account_app
    client = app.test_client()
    login(client)
    db = app.extensions["cloud"].active().db
    older, newer, undated, waiting = [custom(db) for _ in range(4)]
    db.update_personal(older, {"watched_date": "2023-01-01"})
    db.update_personal(newer, {"watched_date": "2025-03-12"})
    db.update_personal(undated, {"watched_date": None})
    db.update_personal(waiting, {"status": "Watchlist"})
    db.update_personal(older, {"note": "editing this must not move it to the top"})
    html = client.get("/account?view=personal").get_data(as_text=True)
    assert shelf_ids(html, "recent") == [newer, older]
    assert '<time datetime="2025-03-12">' in html
    db.update_personal(older, {"watched_date": None})
    db.update_personal(newer, {"watched_date": None})
    html = client.get("/account?view=personal").get_data(as_text=True)
    assert "Recently added" in html
    assert shelf_ids(html, "recent") == [waiting, undated, newer, older]
    assert "<time " not in html


def test_editing_and_settings_are_separate_and_validation_keeps_draft(account_app):
    app, fake, _ = account_app
    client = app.test_client()
    login(client)
    html = client.get("/account?flow=edit-profile").get_data(as_text=True)
    assert html.count('name="avatar_id"') == 16
    assert 'name="display_name"' in html
    assert 'data-profile-shelf="' not in html
    response = post(
        client, "/account/profile", display_name="<Draft>", avatar_id="invalid"
    )
    assert response.status_code == 422
    assert 'value="&lt;Draft&gt;"' in response.get_data(as_text=True)
    assert b"data-profile-editor" in response.data
    html = client.get("/account/settings").get_data(as_text=True)
    assert 'action="/account/sync-settings"' in html
    assert 'action="/account/signout"' in html
    nav = html.split('<nav class="app-nav"', 1)[1].split("</nav>", 1)[0]
    assert nav.count('aria-current="page"') == 1
    assert re.search(r'href="/settings"\s+aria-current="page"', nav)
    response = post(client, "/account/sync-settings", enabled="0")
    assert response.location.endswith("/account/settings")
    assert not app.extensions["cloud"].status()["enabled"]
    post(client, "/account/profile", display_name="Offline name", avatar_id="cat-mint")
    assert app.extensions["cloud"].status()["profile"]["display_name"] == "Offline name"
    assert not any(call[0] == "profile" for call in fake.calls)


def test_profile_translates_cached_names_without_changing_movie_identity(account_app):
    app, _, _ = account_app
    client = app.test_client()
    login(client)
    cloud = app.extensions["cloud"]
    raw = dict(
        MOVIE,
        title="The Class",
        original_title="Hababam Sınıfı",
        original_language="tr",
    )
    app.extensions["tmdb"].get = lambda *args, **kwargs: raw
    details = cloud.active().catalog.details(603)
    mid, _ = cloud.active().db.add_tmdb(
        {"tmdb_id": details["tmdb_id"], "title": details["title"], "status": "Watched"}
    )
    cloud.active().db.update_personal(mid, {"favorite": 1})
    before = cloud.active().db.movie(mid)
    post(client, "/settings/language", language="tr")
    html = client.get("/account?view=personal").get_data(as_text=True)
    assert "Hababam Sınıfı" in html and "Favorilerim" in html
    assert f'href="/movie/{mid}"' in html
    post(client, "/settings/language", language="en")
    html = client.get("/account?view=personal").get_data(as_text=True)
    assert "The Class" in html
    assert cloud.active().db.movie(mid) == before
    assert (
        json.loads(
            cloud.active().db.query("SELECT data_json FROM movie_metadata")[0][
                "data_json"
            ]
        )["details"]["tmdb_id"]
        == 603
    )


def test_conflict_details_remain_available_only_in_account_settings(account_app):
    app, fake, _ = account_app
    client = app.test_client()
    login(client)
    cloud = app.extensions["cloud"]
    db = cloud.active().db
    mid = custom(db, "Original private note")
    cloud.run_once()
    key = db.movie(mid)["record_key"]
    fake.records[(A, key)]["data"]["note"] = "Remote private note"
    fake.records[(A, key)]["revision"] += 1
    fake.revisions[A] += 1
    db.update_personal(mid, {"note": "Local private note"})
    cloud.run_once()
    assert cloud.status()["conflicts"] == 1
    overview = client.get("/account?view=personal").get_data(as_text=True)
    assert (
        "Local private note" not in overview and "Remote private note" not in overview
    )
    assert "data-profile-sync-notice" in overview
    settings = client.get("/account/settings").get_data(as_text=True)
    assert "Local private note" in settings and "Remote private note" in settings
    assert 'id="conflicts"' in settings
    response = post(
        client, "/account/resolve", record_key=key, choice="invalid", revision="2"
    )
    assert response.status_code == 409
    nav = (
        response.get_data(as_text=True)
        .split('<nav class="app-nav"', 1)[1]
        .split("</nav>", 1)[0]
    )
    assert re.search(r'href="/settings"\s+aria-current="page"', nav)


@pytest.mark.parametrize(
    "flow", ["edit-profile", "personalize", "edit-showcase", "settings"]
)
def test_owner_controls_require_signin(account_app, flow):
    app, _, _ = account_app
    client = app.test_client()
    html = client.get("/account?flow=" + flow).get_data(as_text=True)
    assert 'action="/account/signin"' in html
    assert 'name="avatar_id"' not in html
    assert 'action="/account/signout"' not in html
