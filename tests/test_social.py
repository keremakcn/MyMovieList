"""Public discovery contracts, privacy boundaries and in-app navigation."""

import json
from copy import deepcopy
from datetime import date, timedelta
from uuid import uuid4

import pytest
from test_app import mock_tmdb
from test_cloud_sync import MemorySessions, StubOpener
from test_usernames import UsernameCloud

from app import create_app
from cloud_client import CloudError, SupabaseClient
from social import decode_cursor, encode_cursor, normalize_query, validate_page
from tmdb_client import TMDBError

TODAY = date(2026, 10, 8)


def person(username="deniz", display_name="Deniz"):
    return {
        "username": username,
        "display_name": display_name,
        "avatar_id": "cat-lilac",
    }


def page(view="people", rows=None, cursor=None):
    today = TODAY
    start = today - timedelta(days=today.weekday())
    return {
        "protocol": 1,
        "view": view,
        "rows": rows or [],
        "next_cursor": cursor,
        "week_start": start.isoformat(),
        "week_end": (start + timedelta(days=6)).isoformat(),
    }


def watch(username="deniz", **extra):
    return dict(person(username), tmdb_id=603, watched_date=TODAY.isoformat(), **extra)


class SocialCloud(UsernameCloud):
    def __init__(self):
        super().__init__()
        self.members = [person(), person("mert", "Deniz")]
        self.watches = [watch(rating=9), watch("mert")]
        self.missing_social = False

    def social_page(self, view="people", query="", cursor=None):
        self.health()
        self.calls.append(("social", view, query, cursor))
        if self.missing_social:
            raise CloudError("Missing discovery setup.", "setup")
        rows = self.members if view == "people" else self.watches
        rows = [
            row
            for row in rows
            if not query
            or query.lower() in (row["display_name"] + " " + row["username"]).lower()
        ]
        if cursor:
            rows = [row for row in rows if row["username"] > cursor["username"]]
        cap = 16 if view == "people" else 12
        position = {"username": rows[cap - 1]["username"]} if len(rows) > cap else None
        return validate_page(page(view, deepcopy(rows[:cap]), position), view)

    def public_profile_by_username(self, username):
        member = next(
            (row for row in self.members if row["username"] == username), None
        )
        if not member:
            return {"found": False}
        return dict(member, found=True, share_id=str(uuid4()), films=[{"tmdb_id": 603}])


@pytest.fixture
def social_app(tmp_path):
    fake = SocialCloud()
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "synthetic-social-test",
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


def test_public_http_contract_uses_fixed_rpc_without_account_token():
    opener = StubOpener(json.dumps(page(rows=[person()])).encode())
    client = SupabaseClient(
        "https://example.supabase.co", "sb_publishable_test", opener
    )
    assert client.social_page(query=" @deniz ")["rows"] == [person()]
    req, timeout = opener.requests[0]
    assert req.full_url.endswith("/rest/v1/rpc/mml_social_page")
    assert json.loads(req.data) == {
        "p_view": "people",
        "p_query": "deniz",
        "p_cursor": None,
    }
    assert req.get_header("Authorization") is None
    assert req.get_header("Apikey") == "sb_publishable_test" and timeout == 12


def test_cursor_roundtrip_is_bound_to_view_and_search():
    position = {"username": "deniz"}
    token = encode_cursor("people", "Deniz", position)
    assert decode_cursor(token, "people", "Deniz") == position
    for view, query in [("week", "Deniz"), ("people", "another")]:
        with pytest.raises(ValueError):
            decode_cursor(token, view, query)


@pytest.mark.parametrize("token", ["broken!", "x" * 1025, "bnVsbA", "e30", "W10"])
def test_invalid_cursors_are_rejected(token):
    with pytest.raises(ValueError):
        decode_cursor(token, "people", "")


@pytest.mark.parametrize("query", [None, [], "x" * 61, "a\nb", "a\x00b", "a\x7fb"])
def test_search_input_is_bounded(query):
    with pytest.raises(ValueError):
        normalize_query(query)


@pytest.mark.parametrize(
    "field,value",
    [
        ("note", "PRIVATE"),
        ("email", "private@example.test"),
        ("avatar_id", "../private"),
        ("avatar_id", []),
        ("username", "INVALID"),
        ("display_name", "x" * 41),
    ],
)
def test_member_projection_rejects_private_or_malformed_fields(field, value):
    data = page(rows=[dict(person(), **{field: value})])
    with pytest.raises(ValueError):
        validate_page(data, "people")


@pytest.mark.parametrize(
    "field,value",
    [
        ("note", "PRIVATE"),
        ("favorite", True),
        ("rating", True),
        ("rating", 11),
        ("tmdb_id", True),
        ("tmdb_id", 0),
        ("watched_date", "2026-02-30"),
        ("watched_date", "2020-01-01"),
    ],
)
def test_weekly_projection_rejects_invalid_data(field, value):
    data = page("week", [dict(watch(), **{field: value})])
    with pytest.raises(ValueError):
        validate_page(data, "week")


def test_pagination_order_sizes_and_cursor_must_match_last_row():
    rows = [person(f"reader{i:03}") for i in range(16)]
    valid = page(rows=rows, cursor={"username": "reader015"})
    assert validate_page(valid, "people")["rows"] == rows
    for bad in [
        page(rows=rows + [person("reader016")]),
        page(rows=rows[::-1]),
        page(rows=[person(), person()]),
        page(rows=rows, cursor={"username": "reader014"}),
        page(rows=[person()], cursor={"username": "deniz"}),
        dict(valid, protocol=True),
        dict(valid, private_library=[]),
        dict(valid, week_end="2020-01-01"),
    ]:
        with pytest.raises(ValueError):
            validate_page(bad, "people")


def test_week_pages_allow_same_movie_for_different_members():
    data = page("week", [watch(rating=10), watch("mert")])
    assert validate_page(data, "week") == data
    with pytest.raises(ValueError):
        validate_page(page("week", [watch(), watch()]), "week")


def test_guest_directory_links_to_profile_and_never_imports_private_library(social_app):
    app, fake = social_app
    client = app.test_client()
    response = client.get("/social")
    assert (
        response.status_code == 200 and response.headers["Cache-Control"] == "no-store"
    )
    text = response.get_data(as_text=True)
    assert "/profiles/u/deniz" in text and "Public showcases" in text
    assert "post composer" not in text and "/account/signup" not in text
    profile = client.get("/profiles/u/deniz")
    assert profile.status_code == 200 and b"The Matrix" in profile.data
    assert b"Back to Social" in profile.data
    assert client.get("/catalog_movie/603").status_code == 200
    assert app.extensions["cloud"].guest.query("SELECT * FROM movies") == []
    assert not [call for call in fake.calls if call[0] in ("signin", "push")]


def test_weekly_hydrates_each_unique_film_once_and_preserves_own_data(
    social_app, monkeypatch
):
    app, _ = social_app
    library = app.extensions["cloud"].current()
    mid, _ = library.db.add_tmdb(
        {
            "tmdb_id": 603,
            "title": "The Matrix",
            "status": "Watched",
            "note": "PRIVATE-JOURNAL",
            "rating": 4,
            "favorite": 1,
        }
    )
    before = library.db.movie(mid)
    calls = []
    details = library.catalog.details

    def counted(mid):
        calls.append(mid)
        return details(mid)

    monkeypatch.setattr(library.catalog, "details", counted)
    client = app.test_client()
    response = client.get("/social?view=week")
    assert response.status_code == 200
    assert calls == [603]
    text = response.get_data(as_text=True)
    assert text.count('class="social-activity-card"') == 2
    assert "PRIVATE-JOURNAL" not in text and "9/10" in text and "4/10" not in text
    assert f'href="/movie/{mid}"' in text
    assert client.get(f"/movie/{mid}").status_code == 200
    after = library.db.movie(mid)
    for key in (
        "note",
        "rating",
        "favorite",
        "status",
        "watched_date",
        "created_at",
        "record_key",
    ):
        assert after[key] == before[key]


def test_catalog_outage_keeps_member_and_week_visible(social_app, monkeypatch):
    app, _ = social_app
    library = app.extensions["cloud"].current()

    def unavailable(mid):
        raise TMDBError("offline")

    monkeypatch.setattr(library.catalog, "details", unavailable)
    response = app.test_client().get("/social?view=week")
    assert response.status_code == 200 and b"#603" in response.data
    assert b"Deniz" in response.data and b"/catalog_movie/603" in response.data


def test_search_pagination_and_clear_are_native_navigation(social_app):
    app, fake = social_app
    client = app.test_client()
    assert b"@deniz" not in client.get("/social?q=%40mert").data
    assert fake.calls[-1] == ("social", "people", "mert", None)
    response = client.get("/social?q=not-a-member")
    assert (
        b"No matching public profiles." in response.data
        and b"Clear search" in response.data
    )
    fake.members = [person(f"reader{i:03}") for i in range(18)]
    response = client.get("/social")
    assert b"Next page" in response.data and b"reader016" not in response.data
    token = encode_cursor("people", "", {"username": "reader015"})
    response = client.get("/social", query_string={"cursor": token})
    assert b"reader016" in response.data and b"reader015" not in response.data


@pytest.mark.parametrize(
    "params",
    [
        {"view": "posts"},
        {"q": "x" * 61},
        {"cursor": "invalid!"},
        {"q": "a\x00b"},
        {"cursor": encode_cursor("people", "another", {"username": "deniz"})},
    ],
)
def test_invalid_navigation_never_calls_provider(social_app, params):
    app, fake = social_app
    response = app.test_client().get("/social", query_string=params)
    assert response.status_code == 400 and b"Check your search" in response.data
    assert fake.calls == []


@pytest.mark.parametrize("state", ["offline", "setup", "malformed"])
def test_outage_setup_and_bad_provider_are_clear_not_a_user_input_error(
    social_app, monkeypatch, state
):
    app, fake = social_app
    if state == "offline":
        fake.offline = True
    elif state == "setup":
        fake.missing_social = True
    else:
        monkeypatch.setattr(fake, "social_page", lambda *args: {"PRIVATE": "SECRET"})
    response = app.test_client().get("/social")
    assert response.status_code == 503 and b"SECRET" not in response.data
    assert b"Your saved library is still available." in response.data
    assert app.test_client().get("/").status_code == 200


@pytest.mark.parametrize("locale,title", [("en", "Social"), ("tr", "Sosyal")])
def test_translation_empty_states_and_navigation(social_app, locale, title):
    app, fake = social_app
    app.extensions["cloud"].guest.execute(
        "INSERT OR REPLACE INTO settings VALUES ('ui_language',?)", locale
    )
    fake.members, fake.watches = [], []
    client = app.test_client()
    response = client.get("/social")
    assert (
        response.status_code == 200
        and f'<html lang="{locale}">'.encode() in response.data
    )
    assert title.encode() in response.data
    assert (
        "No public showcases yet." if locale == "en" else "Henüz açık vitrin yok."
    ).encode() in response.data
    assert client.get("/social?view=week").status_code == 200


def test_android_allowlist_includes_all_new_shared_modules():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    gradle = (root / "android/app/build.gradle").read_text()
    for name in ("social", "social_routes", "public_catalog"):
        assert f"'{name}.py'" in gradle
