"""UI language cannot change movie identity, personal data or filter values."""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_app import MOVIE, mock_tmdb, post

import i18n
from app import create_app
from storage import Database
from tmdb_client import TMDBError


def configuration(folder, detector):
    return {
        "TESTING": True,
        "SECRET_KEY": "language-test",
        "DATA_DIR": str(folder),
        "DATABASE": str(folder / "library.db"),
        "UI_LANGUAGE_DETECTOR": detector,
    }


@pytest.mark.parametrize(
    "os_language,expected", [("tr", "tr"), ("en", "en"), ("de", "en")]
)
def test_detect_only_once_and_remember_manual_choice(tmp_path, os_language, expected):
    detector = Mock(return_value=os_language)
    first = create_app(configuration(tmp_path, detector))
    assert first.test_client().get("/settings").headers["Content-Language"] == expected
    detector.assert_called_once_with()
    client = first.test_client()
    opposite = "en" if expected == "tr" else "tr"
    assert post(client, "/settings/language", language=opposite).status_code == 303
    first.test_client().get("/settings")
    never_detect_again = Mock(
        side_effect=AssertionError("Saved language must bypass OS detection")
    )
    second = create_app(configuration(tmp_path, never_detect_again))
    response = second.test_client().get("/settings")
    assert response.headers["Content-Language"] == opposite
    assert f'<html lang="{opposite}">'.encode() in response.data
    never_detect_again.assert_not_called()
    # All clients see the same device preference; there is no session-only locale.
    assert first.test_client().get("/").headers["Content-Language"] == opposite


@pytest.mark.parametrize(
    "value,expected",
    [
        ("tr_TR.UTF-8", "tr"),
        ("tr-TR", "tr"),
        ("Turkish_Turkey", "tr"),
        ("en_US", "en"),
        ("de-DE", "en"),
        (None, "en"),
    ],
)
def test_system_language_normalization(value, expected):
    assert i18n.normalize_language(value) == expected


@pytest.mark.parametrize(
    "identifier,expected", [(0x041F, "tr"), (0x0409, "en"), (0x0407, "en")]
)
def test_windows_uses_ui_language_not_regional_format(
    monkeypatch, identifier, expected
):
    getter = Mock(return_value=identifier)
    monkeypatch.setattr(i18n.sys, "platform", "win32")
    monkeypatch.setattr(
        i18n.ctypes,
        "WinDLL",
        lambda *a, **kw: SimpleNamespace(GetUserDefaultUILanguage=getter),
        raising=False,
    )
    monkeypatch.setattr(
        i18n.locale,
        "getlocale",
        Mock(
            side_effect=AssertionError(
                "Do not use regional format when UI language is available"
            )
        ),
    )
    assert i18n.detect_system_language() == expected
    getter.assert_called_once_with()


def test_first_start_initialization_is_atomic(tmp_path):
    db = Database(tmp_path / "concurrent.db")
    db.migrate()
    detector = Mock(return_value="tr")
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: i18n.initialize_language(db, detector), range(4)))
    assert db.query("SELECT value FROM settings WHERE key='ui_language'") == [
        {"value": "tr"}
    ]
    detector.assert_called_once_with()


def test_translation_placeholders_and_client_catalog_are_complete():
    pattern = r"\{([a-z_]+)\}"
    for original, translated in i18n.TRANSLATIONS.items():
        assert set(re.findall(pattern, original)) == set(
            re.findall(pattern, translated)
        ), original
    static = Path(__file__).resolve().parents[1] / "static"
    for name in ("script.js", "recommendations.js", "discovery.js"):
        source = (static / name).read_text(encoding="utf-8")
        ui_keys = {
            match[2]
            for match in re.finditer(r"(['\"])([^'\"\n]+)\1", source)
            if match[2] in i18n.TRANSLATIONS
        }
        assert ui_keys <= i18n.CLIENT_MESSAGES


def test_saved_language_api_is_read_only_and_never_rechecks_os(app, client):
    detector = Mock(
        side_effect=AssertionError("OS detection belongs to the first start only")
    )
    app.config["UI_LANGUAGE_DETECTOR"] = detector
    for language in ("tr", "en"):
        post(client, "/settings/language", language=language)
        assert client.get("/api/ui-language").json == {"language": language}
    detector.assert_not_called()


def seed_library(app):
    db = app.extensions["db"]
    for index, title in enumerate(("Settings", "Watched", "The Matrix")):
        db.add_tmdb(
            {
                "tmdb_id": 603 + index,
                "title": title,
                "genre": "Drama, Science Fiction",
                "year": 1999,
                "status": "Watched" if index == 1 else "Watchlist",
                "rating": 8 + index,
                "favorite": 1,
                "note": "Settings / Watched / Your note\nKendi notum: I liked this film.",
                "overview": "Overview is movie content, not interface text.",
                "runtime": 136,
                "score_percent": 82,
                "director": "Director",
                "cast_list": "Actor",
                "watched_date": "2020-02-01",
                "entities_json": json.dumps(
                    {
                        "cast": [{"id": 6384, "name": "Actor"}],
                        "directors": [],
                        "writers": [],
                        "producers": [],
                        "companies": [{"id": 174, "name": "Settings"}],
                    }
                ),
                "poster_path": "/posters/603.jpg",
                "created_at": "2019-01-01T00:00:00Z",
                "updated_at": "2020-02-01T00:00:00Z",
            }
        )
    db.remove(3)
    return db


def test_switch_preserves_every_library_field_and_primary_key(app, client):
    mock_tmdb(app)
    db = seed_library(app)
    original = db.query("SELECT * FROM movies ORDER BY id")
    version = db.query("PRAGMA user_version")
    for language in ("tr", "en", "tr", "en"):
        response = post(client, "/settings/language", language=language)
        assert response.status_code == 303 and response.location == "/settings"
        assert db.query("SELECT * FROM movies ORDER BY id") == original
        assert db.query("PRAGMA user_version") == version
        for path in (
            "/",
            "/?status=Watched",
            "/?status=Watchlist",
            "/?status=trash",
            "/movie/1",
            "/edit/1",
        ):
            response = client.get(path)
            assert response.status_code == 200
            assert response.headers["Content-Language"] == language
        html = client.get("/?status=Watchlist&sort=added_asc&q=Settings").get_data(
            as_text=True
        )
        assert 'href="/movie/1?' in html and ">Settings</a>" in html
        assert 'value="Watchlist"' in html and 'value="Watched"' in html
        assert 'value="added_asc" selected' in html
        assert 'data-movie-id="2"' not in html
        if language == "tr":
            assert "Kütüphanen" in html and "İzlemek istiyorum" in html
        else:
            assert "Your library" in html and "Want to watch" in html
        edit = client.get("/edit/1").get_data(as_text=True)
        assert original[0]["note"] in edit
        assert "Drama, Science Fiction" in html


def test_undo_after_language_switch_retains_metadata_and_order(app, client):
    db = seed_library(app)
    before = db.movie(2)
    marker = post(client, "/delete/2").json["marker"]
    post(client, "/settings/language", language="tr")
    assert post(client, "/restore/2", marker=marker).status_code == 200
    after = db.movie(2)
    assert after == before
    assert [
        row["id"]
        for row in db.query("SELECT * FROM movies WHERE deleted_at IS NULL ORDER BY id")
    ] == [1, 2]


@pytest.mark.parametrize("language", ["en", "tr"])
def test_search_suggestions_and_add_use_fixed_movie_ids_and_provider_language(
    app, client, language
):
    calls = []

    def get(path, **params):
        calls.append((path, dict(params)))
        if path == "search/person":
            return {
                "results": [
                    {
                        "id": 6384,
                        "name": "Settings",
                        "known_for_department": "Acting",
                        "known_for": [dict(MOVIE, media_type="movie")],
                    }
                ],
                "total_pages": 1,
            }
        if path.startswith("movie/"):
            mid = int(path.split("/")[1])
            return dict(MOVIE, id=mid, title="Watched", poster_path=None)
        return {
            "results": [dict(MOVIE, title="Settings", poster_path=None)],
            "total_pages": 1,
        }

    app.extensions["tmdb"].get = get
    post(client, "/settings/language", language=language)
    html = client.get("/search?q=Settings").get_data(as_text=True)
    assert ">Settings</a>" in html
    assert 'name="movie_id" value="603"' in html
    suggestions = client.get("/api/suggestions?q=Settings").json["results"]
    assert all(result["label"] == "Settings" for result in suggestions)
    assert suggestions[0]["url"] == "/catalog_movie/603"
    assert suggestions[1]["url"] == "/explore/person/6384"
    assert suggestions[1]["subtitle"].startswith(
        "Oyuncu" if language == "tr" else "Actor"
    )
    added = post(client, "/add_from_catalog", movie_id=603)
    assert added.json["created"] is True
    duplicate = post(client, "/add_from_catalog", movie_id=603)
    assert duplicate.json["created"] is False
    row = app.extensions["db"].movie(added.json["id"])
    assert (row["tmdb_id"], row["title"], row["status"]) == (
        603,
        "Watched",
        "Watchlist",
    )
    assert all(
        params["language"]
        == ("en-US" if path.startswith("movie/") or language == "en" else "tr-TR")
        for path, params in calls
    )


@pytest.mark.parametrize(
    "path",
    [
        "/search?q=matrix",
        "/catalog_movie/603",
        "/explore/person/6384",
        "/explore/company/174",
        "/taste",
        "/recommendations",
        "/discover/genres",
    ],
)
def test_all_pages_render_in_turkish_without_translating_content(app, client, path):
    mock_tmdb(app)
    post(client, "/settings/language", language="tr")
    response = client.get(path)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert '<html lang="tr">' in html
    assert "Kütüphane" in html and "Ayarlar" in html
    assert "{{ t(" not in html
    if path in (
        "/search?q=matrix",
        "/catalog_movie/603",
        "/explore/person/6384",
        "/explore/company/174",
    ):
        assert "The Matrix" in html
    if path == "/catalog_movie/603":
        assert "A simulated reality." in html and "Science Fiction" in html


def test_ajax_discovery_localizes_ui_while_provider_data_stays_canonical(app, client):
    calls = []

    def get(path, **params):
        calls.append((path, params))
        return {
            "results": [dict(MOVIE, title="Settings", adult=False, video=False)],
            "total_pages": 2,
        }

    app.extensions["tmdb"].get = get
    post(client, "/settings/language", language="tr")
    response = client.get("/api/discovery/trending")
    assert response.status_code == 200 and response.headers["Content-Language"] == "tr"
    assert ">Settings</a>" in response.json["html"]
    assert "İzlemek istiyorum" in response.json["html"]
    assert calls[0][1]["language"] == "tr-TR"


@pytest.mark.parametrize(
    "invalid", ["fr", "tr-TR", "", "TR", "Watched", "../tr", "<script>"]
)
def test_invalid_language_never_changes_preference_or_library(app, client, invalid):
    db = seed_library(app)
    snapshot = db.query("SELECT * FROM movies ORDER BY id")
    response = post(client, "/settings/language", language=invalid)
    assert response.status_code == 400
    assert db.query("SELECT value FROM settings WHERE key='ui_language'") == [
        {"value": "en"}
    ]
    assert db.query("SELECT * FROM movies ORDER BY id") == snapshot


def test_language_change_requires_csrf_and_has_no_open_redirect(app, client):
    assert client.post("/settings/language", data={"language": "tr"}).status_code == 400
    assert (
        post(
            client, "/settings/language", language="tr", next="https://evil.test"
        ).location
        == "/settings"
    )
    assert client.get("/settings/language?language=en").status_code == 405
    assert app.extensions["db"].query(
        "SELECT value FROM settings WHERE key='ui_language'"
    ) == [{"value": "tr"}]


def test_turkish_errors_and_validation_preserve_form_data(app, client):
    post(client, "/settings/language", language="tr")
    response = post(
        client,
        "/add",
        title="Settings",
        status="Watchlist",
        rating="11",
        note="Your note",
    )
    assert response.status_code == 422
    assert "Puan 1 ile 10 arasında olmalı." in response.get_data(as_text=True)
    assert 'value="Settings"' in response.get_data(as_text=True)
    app.extensions["tmdb"].get = Mock(
        side_effect=TMDBError(
            "Movie discovery is temporarily unavailable. Please try again."
        )
    )
    response = client.get("/api/discovery/trending")
    assert "Keşif servisi" in response.json["error"]
    assert client.get("/").status_code == 200


def test_titles_and_notes_are_escaped_in_both_languages(app, client):
    title = '<script>alert("Settings")</script>'
    note = '<img src=x onerror=alert("Watched")>'
    app.extensions["db"].add_tmdb(
        {"tmdb_id": 777, "title": title, "note": note, "status": "Watchlist"}
    )
    for language in ("tr", "en"):
        post(client, "/settings/language", language=language)
        html = client.get("/").get_data(as_text=True)
        assert title not in html and note not in html
        assert "&lt;script&gt;" in html and "&lt;img" in html
        assert app.extensions["db"].movie(1)["title"] == title


@pytest.mark.parametrize("language", ["tr", "en"])
def test_wrong_provider_movie_never_changes_the_library(app, client, language):
    db = seed_library(app)
    before = db.query("SELECT * FROM movies ORDER BY id")
    post(client, "/settings/language", language=language)
    app.extensions["tmdb"].get = Mock(
        return_value=dict(MOVIE, id=999, title="Wrong movie")
    )
    added = post(client, "/add_from_catalog", movie_id=777)
    assert added.status_code == 502
    details = client.get("/catalog_movie/603")
    assert details.status_code == 502 and b"Wrong movie" not in details.data
    refreshed = post(client, "/movie/1/refresh")
    assert refreshed.status_code == 502
    assert db.query("SELECT * FROM movies ORDER BY id") == before


def test_partial_search_failure_is_localized_without_touching_results(app, client):
    mock_tmdb(app)
    original = app.extensions["tmdb"].get

    def get(path, **params):
        if path == "search/movie":
            raise TMDBError(
                "Movie discovery is temporarily unavailable. Please try again."
            )
        return original(path, **params)

    app.extensions["tmdb"].get = get
    post(client, "/settings/language", language="tr")
    html = client.get("/search?q=matrix").get_data(as_text=True)
    assert "Filmler: Keşif servisi geçici olarak kullanılamıyor." in html
    assert "Keanu Reeves" in html
    assert "Showing the other available results" not in html
