"""Explicit profile selections, stable cross-device identity and private defaults."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from test_app import MOVIE, mock_tmdb, post
from test_cloud_sync import A, MemorySessions, custom, login
from test_cloud_sync import account_app as make_account_app
from test_profile_showcase import shelf_ids

from account_profile import (
    ProfileStore,
    remote_profile,
    showcase_settings,
    validate_showcase,
)
from app import create_app
from storage import Database


@pytest.fixture
def account_app(tmp_path):
    yield from make_account_app.__wrapped__(tmp_path)


def select(client, keys, **flags):
    return post(client, "/account/showcase", record_keys=json.dumps(keys), **flags)


def picks(keys, **flags):
    return dict(record_keys=keys, show_ratings=False, show_stats=False, **flags)


def test_default_is_empty_even_with_favorites_and_private_overview_remains(account_app):
    app, _, _ = account_app
    client = app.test_client()
    login(client)
    db = app.extensions["cloud"].active().db
    for _ in range(8):
        custom(db, "PRIVATE-NOTE")
    html = client.get("/account").get_data(as_text=True)
    assert shelf_ids(html, "showcase") == []
    assert 'data-profile-shelf="favorites"' not in html
    assert 'data-profile-shelf="recent"' not in html
    assert "data-profile-stat=" not in html
    assert 'href="/?status=favorite"' not in html
    assert "PRIVATE-NOTE" not in html
    assert "Nothing is added automatically" in html
    personal = client.get("/account?view=personal").get_data(as_text=True)
    assert len(shelf_ids(personal, "favorites")) == 6
    assert personal.count("data-profile-stat=") == 4


def test_explicit_order_opt_in_ratings_counts_and_favorites_are_independent(
    account_app,
):
    app, _, _ = account_app
    client = app.test_client()
    login(client)
    library = app.extensions["cloud"].active()
    ids = [custom(library.db, "PRIVATE-NOTE") for _ in range(4)]
    library.db.update_personal(ids[1], {"favorite": 0})
    chosen = [ids[2], ids[1]]
    keys = [library.db.movie(mid)["record_key"] for mid in chosen]
    before = library.db.query("SELECT * FROM movies")
    assert select(client, keys).status_code == 303
    html = client.get("/account").get_data(as_text=True)
    assert shelf_ids(html, "showcase") == chosen
    assert 'class="profile-film-rating"' not in html
    assert "data-profile-stat=" not in html
    assert "PRIVATE-NOTE" not in html
    assert select(client, keys, show_ratings="1", show_stats="1").status_code == 303
    html = client.get("/account").get_data(as_text=True)
    assert html.count('class="profile-film-rating"') == 2
    assert html.count("data-profile-stat=") == 4
    assert library.db.query("SELECT * FROM movies") == before
    assert select(client, []).status_code == 303
    assert shelf_ids(client.get("/account").get_data(as_text=True), "showcase") == []
    assert library.db.query("SELECT * FROM movies") == before


def test_selected_delete_is_hidden_and_undo_returns_same_position(account_app):
    app, _, _ = account_app
    client = app.test_client()
    login(client)
    library = app.extensions["cloud"].active()
    first, second, third = [custom(library.db) for _ in range(3)]
    keys = [library.db.movie(mid)["record_key"] for mid in (second, first, third)]
    select(client, keys)
    marker = library.db.remove(first)
    assert shelf_ids(client.get("/account").get_data(as_text=True), "showcase") == [
        second,
        third,
    ]
    assert (
        showcase_settings(library.profile.snapshot()["profile"])["record_keys"] == keys
    )
    # Editing flags must not lose a temporarily removed selection.
    assert select(client, keys, show_stats="1").status_code == 303
    assert library.db.restore(first, marker)
    assert shelf_ids(client.get("/account").get_data(as_text=True), "showcase") == [
        second,
        first,
        third,
    ]


@pytest.mark.parametrize(
    "keys,flags",
    [
        (["tmdb:1"] * 7, {}),
        (["tmdb:1", "tmdb:1"], {}),
        (["tmdb:999999999999"], {}),
        (["<script>"], {}),
        ("tmdb:1", {}),
        ([1], {}),
        ([], {"show_stats": "true"}),
    ],
)
def test_tampered_selection_is_rejected_without_overwriting_existing(
    account_app, keys, flags
):
    app, _, _ = account_app
    client = app.test_client()
    login(client)
    library = app.extensions["cloud"].active()
    key = library.db.movie(custom(library.db))["record_key"]
    select(client, [key])
    snapshot = library.profile.snapshot()
    response = select(client, keys, **flags)
    assert response.status_code == 422
    assert b"data-showcase-editor" in response.data
    assert library.profile.snapshot() == snapshot


def test_new_picks_must_belong_to_owner_and_guest_cannot_edit_or_search(account_app):
    app, _, _ = account_app
    cloud = app.extensions["cloud"]
    guest_key = cloud.guest.movie(custom(cloud.guest))["record_key"]
    client = app.test_client()
    assert client.get("/api/account/showcase/films").status_code == 403
    assert select(client, [guest_key]).status_code == 403
    login(client)
    assert select(client, [guest_key]).status_code == 422
    a_key = cloud.active().db.movie(custom(cloud.active().db))["record_key"]
    scope = cloud.scope()
    login(client, "b@example.test")
    assert select(client, [a_key]).status_code == 422
    assert (
        client.get(
            "/api/account/showcase/films", headers={"X-Library-Scope": scope}
        ).status_code
        == 409
    )
    assert client.get("/api/account/showcase/films").json["movies"] == []


def test_local_search_is_paged_bounded_literal_and_does_not_expose_notes(account_app):
    app, _, _ = account_app
    client = app.test_client()
    login(client)
    db = app.extensions["cloud"].active().db
    ids = [custom(db, "PRIVATE-NOTE") for _ in range(25)]
    for index, mid in enumerate(ids):
        db.execute("UPDATE movies SET title=? WHERE id=?", f"Film {index:02}", mid)
    db.execute("UPDATE movies SET title='100%_film' WHERE id=?", ids[0])
    db.remove(ids[-1])
    app.extensions["tmdb"].get = lambda *_args, **_kw: pytest.fail(
        "Picker must stay local"
    )
    first = client.get("/api/account/showcase/films").json
    last = client.get("/api/account/showcase/films?page=999999999999").json
    assert first["page"] == 1 and first["pages"] == 2 and first["count"] == 24
    assert len(first["movies"]) == 20 and len(last["movies"]) == 4 and last["page"] == 2
    assert {m["id"] for m in first["movies"]}.isdisjoint(
        m["id"] for m in last["movies"]
    )
    assert not any(
        "note" in m or "favorite" in m or "rating" in m for m in first["movies"]
    )
    assert "PRIVATE-NOTE" not in json.dumps(first)
    matches = client.get("/api/account/showcase/films", query_string={"q": "%_"}).json
    assert [movie["id"] for movie in matches["movies"]] == [ids[0]]
    assert client.get("/api/account/showcase/films?page=invalid").json["page"] == 1
    empty = client.get("/api/account/showcase/films?q=missing").json
    assert empty["movies"] == [] and empty["pages"] == 1


def test_cached_translation_search_and_showcase_keep_stable_identity(account_app):
    app, _, _ = account_app
    client = app.test_client()
    login(client)
    cloud = app.extensions["cloud"]
    app.extensions["tmdb"].get = lambda *_args, **_kwargs: dict(
        MOVIE,
        title="The Class",
        original_title="Hababam Sınıfı",
        original_language="tr",
    )
    details = cloud.active().catalog.details(603)
    mid, _ = cloud.active().db.add_tmdb({"tmdb_id": 603, "title": details["title"]})
    select(client, ["tmdb:603"])
    before = cloud.active().db.movie(mid)
    post(client, "/settings/language", language="tr")
    app.extensions["tmdb"].get = lambda *_args, **_kwargs: pytest.fail(
        "Cached titles only"
    )
    assert "Hababam Sınıfı" in client.get("/account").get_data(as_text=True)
    result = client.get("/api/account/showcase/films?q=hababam").json["movies"]
    assert result[0]["id"] == mid and result[0]["record_key"] == "tmdb:603"
    assert result[0]["title"] == "Hababam Sınıfı"
    post(client, "/settings/language", language="en")
    assert "The Class" in client.get("/account").get_data(as_text=True)
    assert cloud.active().db.movie(mid) == before


def test_partial_identity_and_showcase_saves_do_not_erase_each_other(account_app):
    app, _, _ = account_app
    client = app.test_client()
    login(client)
    library = app.extensions["cloud"].active()
    key = library.db.movie(custom(library.db))["record_key"]
    select(client, [key], show_ratings="1")
    post(client, "/account/profile", display_name="Deniz", avatar_id="cat-mint")
    profile = library.profile.snapshot()["profile"]
    assert profile["showcase"] == {
        "record_keys": [key],
        "show_stats": False,
        "show_ratings": True,
    }
    select(client, [])
    assert library.profile.snapshot()["profile"]["display_name"] == "Deniz"
    assert library.profile.snapshot()["profile"]["avatar_id"] == "cat-mint"
    # Both screens may submit in parallel; merge happens under SQLite's lock.
    barrier = threading.Barrier(2)

    def save(value):
        barrier.wait(3)
        library.profile.save(value)

    with ThreadPoolExecutor(2) as executor:
        futures = [
            executor.submit(save, value)
            for value in (
                {"display_name": "Concurrent", "avatar_id": "cat-gold"},
                {"showcase": picks([key])},
            )
        ]
        for future in futures:
            future.result(5)
    profile = library.profile.snapshot()["profile"]
    assert profile["display_name"] == "Concurrent" and profile["showcase"][
        "record_keys"
    ] == [key]


def test_offline_restart_and_second_device_resolve_stable_keys_not_local_ids(
    account_app, tmp_path
):
    app, fake, _ = account_app
    client = app.test_client()
    login(client)
    cloud = app.extensions["cloud"]
    library = cloud.active()
    ids = [custom(library.db) for _ in range(3)]
    keys = [library.db.movie(mid)["record_key"] for mid in reversed(ids)]
    fake.offline = True
    select(client, keys, show_ratings="1")
    post(client, "/account/profile", display_name="Deniz", avatar_id="cat-cloud")
    cloud.run_once()
    restarted = Database(library.db.path, A)
    assert (
        ProfileStore(restarted).snapshot()["profile"]["showcase"]["record_keys"] == keys
    )
    assert library.profile.snapshot()["dirty"]
    fake.offline = False
    cloud.states[A]["retry_at"] = 0
    cloud.run_once()
    assert not library.profile.snapshot()["dirty"]
    assert set(fake.profiles[A]) == {"display_name", "avatar_id", "showcase"}
    assert len(json.dumps(fake.profiles[A])) < 600
    assert "PRIVATE" not in json.dumps(fake.profiles[A])
    folder = tmp_path / "second-device"
    folder.mkdir()
    second = create_app(
        {
            "TESTING": True,
            "DATA_DIR": str(folder),
            "DATABASE": str(folder / "guest.db"),
            "SECRET_KEY": "synthetic",
            "BACKGROUND_METADATA": False,
            "UI_LANGUAGE_DETECTOR": lambda: "en",
            "CLOUD_CLIENT": fake,
            "CLOUD_SESSION_STORE": MemorySessions(),
            "CLOUD_ACCOUNTS_READY": True,
        }
    )
    mock_tmdb(second)
    try:
        other = second.test_client()
        login(other)
        other_library = second.extensions["cloud"].active()
        # Metadata is allowed to arrive before the film records.
        assert (
            other_library.profile.snapshot()["profile"]["showcase"]["record_keys"]
            == keys
        )
        assert shelf_ids(other.get("/account").get_data(as_text=True), "showcase") == []
        html = other.get("/account?flow=edit-showcase").get_data(as_text=True)
        assert all(key in html for key in keys)
        assert select(other, keys).status_code == 303
        custom(other_library.db)  # Shift numeric local IDs on the new device.
        second.extensions["cloud"].run_once()
        movies = other_library.db.showcase_films(keys)
        assert [movie["record_key"] for movie in movies] == keys
        assert [movie["id"] for movie in movies] != list(reversed(ids))
        assert shelf_ids(other.get("/account").get_data(as_text=True), "showcase") == [
            movie["id"] for movie in movies
        ]
    finally:
        second.extensions["cloud"].close()


def test_remote_old_or_invalid_optional_settings_do_not_invent_picks_or_lose_identity():
    old = {"display_name": "Deniz", "avatar_id": "cat-mint"}
    assert showcase_settings(old) == picks([])
    invalid = dict(old, showcase={"record_keys": ["not-a-film"]})
    assert remote_profile({"mml_profile": invalid}) == old
    remote = dict(old, showcase=picks(["tmdb:603"]))
    assert remote_profile({"mml_profile": remote}) == remote
    with pytest.raises(ValueError):
        validate_showcase(dict(picks([]), show_ratings=1))


@pytest.mark.parametrize(
    "stored",
    [
        "broken-json",
        "[]",
        '{"profile":{"display_name":"Deniz","avatar_id":"cat-mint","showcase":null}}',
    ],
)
def test_profile_can_recover_from_invalid_local_metadata(account_app, stored):
    app, _, _ = account_app
    client = app.test_client()
    login(client)
    library = app.extensions["cloud"].active()
    library.db.execute(
        "INSERT OR REPLACE INTO settings VALUES ('account_profile',?)", stored
    )
    profile = library.profile.save(
        {"display_name": "Recovered", "avatar_id": "cat-gold"}
    )
    assert profile == {"display_name": "Recovered", "avatar_id": "cat-gold"}
    assert library.profile.snapshot()["dirty"]
