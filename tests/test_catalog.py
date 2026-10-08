"""Credits, bilingual metadata and movie identity across offline reads and upgrades."""

import copy
import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from unittest.mock import Mock

import pytest
from test_app import MOVIE, post

from app import create_app
from storage import Database
from tmdb_client import TMDBError


def turkish_movie(mid=32055):
    return dict(
        copy.deepcopy(MOVIE),
        id=mid,
        title="The Chaos Class",
        original_language="tr",
        original_title="Hababam Sınıfı",
        overview="Students challenge the rules of their school.",
        credits={
            "cast": [
                {"id": 100 + i, "name": f"Actor {i}", "character": f"Role {i}"}
                for i in range(15)
            ],
            "crew": [{"id": 300, "name": "Ertem Eğilmez", "job": "Director"}],
        },
        translations={
            "id": mid,
            "translations": [
                {
                    "iso_639_1": "tr",
                    "iso_3166_1": "TR",
                    "data": {
                        "title": "Hababam Sınıfı",
                        "overview": "Hababam Sınıfı'nın okul maceraları.",
                    },
                }
            ],
        },
    )


def provider(app, raw=None):
    raw = raw or turkish_movie()
    mock = Mock(return_value=raw)
    app.extensions["tmdb"].get = mock
    return mock


@pytest.mark.parametrize("locale", ["en", "tr"])
def test_add_saves_full_credits_and_both_languages_in_one_request(app, client, locale):
    api = provider(app)
    post(client, "/settings/language", language=locale)
    result = post(client, "/add_from_catalog", movie_id=32055)
    assert result.status_code == 200 and result.json["created"]
    api.assert_called_once_with(
        "movie/32055", language="en-US", append_to_response="credits,keywords,translations"
    )
    db = app.extensions["db"]
    row = db.movie(result.json["id"])
    assert row["title"] == "The Chaos Class" and row["tmdb_id"] == 32055
    assert len(json.loads(row["entities_json"])["cast"]) == 15
    assert row["director"] == "Ertem Eğilmez"
    before = dict(row)
    app.extensions["tmdb"].get = Mock(side_effect=TMDBError("Offline"))
    for language, title, overview in [
        ("tr", "Hababam Sınıfı", "Hababam Sınıfı&#39;nın okul maceraları."),
        ("en", "The Chaos Class", "Students challenge the rules of their school."),
    ]:
        post(client, "/settings/language", language=language)
        home = client.get("/").get_data(as_text=True)
        detail = client.get(f"/movie/{row['id']}").get_data(as_text=True)
        edit = client.get(f"/edit/{row['id']}").get_data(as_text=True)
        assert title in home and title in detail and title in edit
        assert overview in detail
        assert "Load actors" not in detail and "refresh-form" not in detail
        assert "Actor 14" in detail and "/explore/person/114" in detail
        assert "/explore/company/174" in detail and "/explore/person/300" in detail
        assert 'class="full-cast"' in detail
        assert db.movie(row["id"]) == before
    app.extensions["tmdb"].get.assert_not_called()


def test_bilingual_details_survive_application_restart_offline(app, client):
    provider(app)
    mid = post(client, "/add_from_catalog", movie_id=32055).json["id"]
    post(
        client,
        "/edit/1",
        rating="9",
        note="Benim özel yorumum",
        watched_date="2020-03-04",
    )
    post(client, "/favorite/1", value="1")
    post(client, "/settings/language", language="tr")
    before = app.extensions["db"].movie(mid)
    restarted = create_app(
        dict(
            app.config,
            UI_LANGUAGE_DETECTOR=Mock(side_effect=AssertionError("Already saved")),
        )
    )
    restarted.extensions["tmdb"].get = Mock(side_effect=TMDBError("Offline"))
    response = restarted.test_client().get(f"/movie/{mid}")
    assert response.status_code == 200
    assert "Hababam Sınıfı" in response.get_data(as_text=True)
    assert "okul maceraları" in response.get_data(as_text=True)
    assert restarted.extensions["db"].movie(mid) == before
    restarted.extensions["tmdb"].get.assert_not_called()


@pytest.mark.parametrize("translation", [{}, {"title": " ", "overview": " \n"}])
def test_missing_turkish_synopsis_uses_english_and_original_turkish_title(
    app, client, translation
):
    raw = turkish_movie()
    raw["translations"]["translations"][0]["data"] = translation
    provider(app, raw)
    post(client, "/settings/language", language="tr")
    html = client.get("/catalog_movie/32055").get_data(as_text=True)
    assert "Hababam Sınıfı" in html and "Students challenge" in html


def test_turkish_overview_does_not_replace_english_original_title(app, client):
    raw = dict(
        turkish_movie(603),
        title="The Matrix",
        original_language="en",
        original_title="The Matrix",
    )
    provider(app, raw)
    post(client, "/settings/language", language="tr")
    html = client.get("/catalog_movie/603").get_data(as_text=True)
    assert "<h1>The Matrix</h1>" in html and "okul maceraları" in html
    assert 'name="movie_id" value="603"' in html


def test_original_turkish_title_takes_priority_over_alternative_translation(
    app, client
):
    raw = turkish_movie()
    raw["translations"]["translations"][0]["data"]["title"] = (
        "Alternative Turkish title"
    )
    provider(app, raw)
    post(client, "/settings/language", language="tr")
    assert "<h1>Hababam Sınıfı</h1>" in client.get("/catalog_movie/32055").get_data(
        as_text=True
    )


def test_preview_then_add_reuses_verified_saved_metadata(app, client):
    api = provider(app)
    assert client.get("/catalog_movie/32055").status_code == 200
    added = post(client, "/add_from_catalog", movie_id=32055)
    assert added.json["created"]
    assert post(client, "/add_from_catalog", movie_id=32055).json["created"] is False
    assert api.call_count == 1
    assert len(app.extensions["db"].query("SELECT * FROM movies")) == 1


def test_older_movie_auto_hydrates_on_detail_without_touching_personal_data(
    app, client
):
    api = provider(app)
    db = app.extensions["db"]
    mid, _ = db.add_tmdb(
        dict(
            tmdb_id=32055,
            title="The Chaos Class",
            status="Watched",
            note="Özel yorum",
            rating=9,
            favorite=1,
            watched_date="1998-01-01",
        )
    )
    before = db.movie(mid)
    post(client, "/settings/language", language="tr")
    html = client.get(f"/movie/{mid}").get_data(as_text=True)
    assert "Hababam Sınıfı" in html and "Actor 14" in html and "okul maceraları" in html
    after = db.movie(mid)
    for key in (
        "id",
        "tmdb_id",
        "title",
        "note",
        "rating",
        "favorite",
        "status",
        "created_at",
        "updated_at",
        "watched_date",
        "deleted_at",
    ):
        assert after[key] == before[key]
    assert after["cast_list"] and after["entities_json"] and after["overview"]
    assert api.call_count == 1
    app.extensions["tmdb"].get = Mock(side_effect=TMDBError("Offline"))
    assert client.get(f"/movie/{mid}").status_code == 200
    app.extensions["tmdb"].get.assert_not_called()


def test_older_library_remains_available_when_auto_fetch_fails(app, client):
    db = app.extensions["db"]
    mid, _ = db.add_tmdb(
        dict(tmdb_id=32055, title="The Chaos Class", note="Keep me", rating=8)
    )
    before = db.movie(mid)
    api = Mock(side_effect=TMDBError("Offline"))
    app.extensions["tmdb"].get = api
    for _ in range(2):
        assert client.get(f"/movie/{mid}").status_code == 200
        assert b"Keep me" in client.get(f"/movie/{mid}").data
    assert db.movie(mid) == before and api.call_count == 1


def test_legacy_truncated_cast_is_saved_in_full_automatically(app, client):
    raw = turkish_movie()
    provider(app, raw)
    db = app.extensions["db"]
    db.add_tmdb(
        dict(
            tmdb_id=32055,
            title="The Chaos Class",
            note="Keep my note",
            rating=9,
            cast_list="Actor 0",
            entities_json=json.dumps({"cast": raw["credits"]["cast"][:1]}),
        )
    )
    before = db.movie(1)
    assert client.get("/movie/1").status_code == 200
    after = db.movie(1)
    assert len(json.loads(after["entities_json"])["cast"]) == 15
    assert "Actor 14" in after["cast_list"]
    for field in (
        "title",
        "note",
        "rating",
        "created_at",
        "updated_at",
        "id",
        "tmdb_id",
    ):
        assert after[field] == before[field]


def test_deleted_film_restores_bilingual_content_and_full_credits_in_original_order(
    app, client
):
    provider(app)
    post(client, "/add_from_catalog", movie_id=32055)
    db = app.extensions["db"]
    db.add_tmdb(dict(tmdb_id=888, title="Other film"))
    post(
        client, "/edit/1", rating="10", note="Keep this note", watched_date="2021-01-01"
    )
    post(client, "/favorite/1", value="1")
    before = db.movie(1)
    metadata = db.query("SELECT * FROM movie_metadata")
    marker = post(client, "/delete/1").json["marker"]
    post(client, "/settings/language", language="tr")
    assert post(client, "/restore/1", marker=marker).status_code == 200
    assert (
        db.movie(1) == before and db.query("SELECT * FROM movie_metadata") == metadata
    )
    html = client.get("/?sort=added_asc").get_data(as_text=True)
    assert html.index('data-movie-id="1"') < html.index('data-movie-id="2"')
    assert "Hababam Sınıfı" in html


@pytest.mark.parametrize(
    "invalid",
    [
        "wrong_id",
        "wrong_translation_id",
        "missing_credits",
        "invalid_cast",
        "null_name",
    ],
)
def test_invalid_metadata_never_creates_or_replaces_a_library_film(
    app, client, invalid
):
    raw = turkish_movie()
    if invalid == "wrong_id":
        raw["id"] = 603
    elif invalid == "wrong_translation_id":
        raw["translations"]["id"] = 603
    elif invalid == "missing_credits":
        raw.pop("credits")
    elif invalid == "invalid_cast":
        raw["credits"]["cast"] = "Not a list"
    else:
        raw["credits"]["cast"][0]["name"] = None
    provider(app, raw)
    assert post(client, "/add_from_catalog", movie_id=32055).status_code == 502
    assert not app.extensions["db"].query("SELECT * FROM movies")
    assert not app.extensions["db"].query("SELECT * FROM movie_metadata")


def test_failed_refresh_keeps_previous_verified_translations_and_personal_data(
    app, client
):
    provider(app)
    post(client, "/add_from_catalog", movie_id=32055)
    db = app.extensions["db"]
    before, cache = db.movie(1), db.query("SELECT * FROM movie_metadata")
    provider(app, turkish_movie(999))
    assert post(client, "/movie/1/refresh").status_code == 502
    assert db.movie(1) == before and db.query("SELECT * FROM movie_metadata") == cache


def test_empty_credits_are_complete_and_do_not_trigger_repeat_requests(app, client):
    raw = dict(
        turkish_movie(), credits={"cast": [], "crew": []}, production_companies=[]
    )
    api = provider(app, raw)
    post(client, "/add_from_catalog", movie_id=32055)
    for _ in range(3):
        assert client.get("/movie/1").status_code == 200
    assert api.call_count == 1


def test_failed_add_retries_after_short_cooldown_without_partial_record(
    app, client, monkeypatch
):
    clock = [100]
    monkeypatch.setattr("catalog.time.monotonic", lambda: clock[0])
    api = Mock(side_effect=[TMDBError("Temporary outage", 503, 3), turkish_movie()])
    app.extensions["tmdb"].get = api
    assert post(client, "/add_from_catalog", movie_id=32055).status_code == 503
    clock[0] += 1
    retry = post(client, "/add_from_catalog", movie_id=32055)
    assert retry.status_code == 503 and retry.json["error"] == "Temporary outage"
    assert api.call_count == 1 and not app.extensions["db"].query(
        "SELECT * FROM movies"
    )
    clock[0] += 3
    assert post(client, "/add_from_catalog", movie_id=32055).json["created"] is True
    assert (
        api.call_count == 2
        and len(app.extensions["db"].query("SELECT * FROM movies")) == 1
    )


def test_rate_limited_metadata_keeps_429_and_provider_message_during_cooldown(
    app, client, monkeypatch
):
    clock = [100]
    monkeypatch.setattr("catalog.time.monotonic", lambda: clock[0])
    api = Mock(
        side_effect=TMDBError(
            "Movie discovery is busy. Please wait a moment and try again.", 429, 60
        )
    )
    app.extensions["tmdb"].get = api
    first = post(client, "/add_from_catalog", movie_id=32055)
    clock[0] += 4
    second = post(client, "/add_from_catalog", movie_id=32055)
    assert first.status_code == second.status_code == 429
    assert first.json == second.json and api.call_count == 1


@pytest.mark.parametrize(
    "query", ["Hababam", "hababam sınıfı", "The Chaos Class", "Chaos", "HABABAM SINIFI"]
)
def test_library_search_matches_both_titles_in_both_languages(app, client, query):
    provider(app)
    post(client, "/add_from_catalog", movie_id=32055)
    for language in ("tr", "en"):
        post(client, "/settings/language", language=language)
        html = client.get("/", query_string={"q": query}).get_data(as_text=True)
        assert 'data-movie-id="1"' in html
        assert ("Hababam Sınıfı" if language == "tr" else "The Chaos Class") in html
    assert 'data-movie-id="1"' not in client.get("/?q=%25").get_data(as_text=True)


@pytest.mark.parametrize(
    "query",
    ["İSTANBUL", "istanbul", "Istanbul", "İstanbul Kırmızısı", "istanbul kirmizisi"],
)
def test_turkish_dotted_and_dotless_letters_match_in_library_search(app, client, query):
    raw = dict(
        turkish_movie(), title="Red Istanbul", original_title="İstanbul Kırmızısı"
    )
    provider(app, raw)
    post(client, "/add_from_catalog", movie_id=32055)
    for language in ("tr", "en"):
        post(client, "/settings/language", language=language)
        html = client.get("/", query_string={"q": query}).get_data(as_text=True)
        assert 'data-movie-id="1"' in html
    assert app.extensions["db"].movie(1)["title"] == "Red Istanbul"


def test_unicode_title_and_synopsis_are_escaped_without_touching_ids(app, client):
    raw = turkish_movie()
    raw["original_title"] = "<script>Hababam</script>"
    raw["translations"]["translations"][0]["data"]["overview"] = (
        "<img src=x onerror=alert(1)>"
    )
    provider(app, raw)
    post(client, "/settings/language", language="tr")
    html = client.get("/catalog_movie/32055").get_data(as_text=True)
    assert "<script>Hababam</script>" not in html and "&lt;script&gt;Hababam" in html
    assert "<img src=x onerror" not in html and "&lt;img src=x" in html
    assert 'name="movie_id" value="32055"' in html


def test_parallel_catalog_requests_fetch_and_save_each_movie_once(app):
    lock = Lock()
    calls = []

    def get(path, **params):
        with lock:
            calls.append(path)
        time.sleep(0.04)
        return turkish_movie()

    app.extensions["tmdb"].get = get
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(
            pool.map(lambda _: app.extensions["catalog"].details(32055), range(6))
        )
    assert calls == ["movie/32055"]
    assert all(result["tmdb_id"] == 32055 for result in results)
    assert len(app.extensions["db"].query("SELECT * FROM movie_metadata")) == 1


def test_visible_legacy_entries_backfill_in_background_once_and_poll_by_id(app, client):
    release = Event()
    entered = Event()
    api_calls = []

    def get(path, **params):
        api_calls.append(path)
        entered.set()
        release.wait(3)
        return turkish_movie()

    app.extensions["tmdb"].get = get
    catalog = app.extensions["catalog"]
    catalog.background = True
    db = app.extensions["db"]
    db.add_tmdb(dict(tmdb_id=32055, title="The Chaos Class"))
    before = db.movie(1)
    try:
        assert client.get("/").status_code == 200
        assert entered.wait(1)
        assert 'data-metadata-pending="1"' in client.get("/").get_data(as_text=True)
        response = client.get("/api/library/metadata?id=1").json
        assert response["movies"][0]["pending"] is True
        release.set()
        for _ in range(100):
            if not catalog.pending:
                break
            time.sleep(0.01)
        assert not catalog.pending
        post(client, "/settings/language", language="tr")
        result = client.get("/api/library/metadata?id=1").json
        assert (
            result["language"] == "tr"
            and result["movies"][0]["title"] == "Hababam Sınıfı"
        )
        assert result["movies"][0]["pending"] is False
        assert api_calls == ["movie/32055"]
        after = db.movie(1)
        for key in ("created_at", "updated_at", "title", "id", "tmdb_id"):
            assert after[key] == before[key]
    finally:
        release.set()
        catalog.close()


@pytest.mark.parametrize(
    "url",
    [
        "/api/library/metadata",
        "/api/library/metadata?id=-1",
        "/api/library/metadata?id=1;DROP",
        "/api/library/metadata?id=" + "9" * 30,
        "/api/library/metadata?" + "&".join("id=1" for _ in range(37)),
    ],
)
def test_metadata_poll_rejects_invalid_or_unbounded_queries(client, url):
    assert client.get(url).status_code == 400


def test_combined_search_discovery_and_taste_use_tr_but_keep_numeric_identity(
    app, client
):
    raw = turkish_movie()
    calls = []

    def get(path, **params):
        calls.append((path, params))
        if path.startswith("movie/"):
            return raw
        if path == "search/person":
            return {
                "results": [
                    {
                        "id": 300,
                        "name": "Ertem Eğilmez",
                        "known_for_department": "Directing",
                        "known_for": [dict(raw, media_type="movie")],
                    }
                ],
                "total_pages": 1,
            }
        localized = dict(
            raw, title="The Chaos Class", overview="Türkçe arama açıklaması"
        )
        return {"results": [localized], "total_pages": 1, "total_results": 1}

    app.extensions["tmdb"].get = get
    post(client, "/settings/language", language="tr")
    html = client.get("/search?q=hababam").get_data(as_text=True)
    assert (
        "Hababam Sınıfı" in html
        and "Türkçe arama açıklaması" in html
        and "Ertem Eğilmez" in html
    )
    assert "/catalog_movie/32055" in html and "/explore/person/300" in html
    suggestions = client.get("/api/suggestions?q=hababam").json["results"]
    assert suggestions[0]["label"] == "Hababam Sınıfı"
    discovery = client.get("/api/discovery/trending").json["html"]
    assert "Hababam Sınıfı" in discovery
    choices = client.get("/api/taste/choices?q=hababam").json["movies"]
    assert choices[0]["tmdb_id"] == 32055 and choices[0]["title"] == "Hababam Sınıfı"
    assert all(params["language"] == "tr-TR" for _, params in calls)
    assert post(client, "/taste/save", movie_id=["32055"]).json["created"] == 1
    assert calls[-1][1]["language"] == "en-US"
    assert calls[-1][1]["append_to_response"] == "credits,keywords,translations"
    assert app.extensions["db"].movie(1)["title"] == "The Chaos Class"


def test_language_projection_does_not_rerank_or_mutate_recommendation_selection(
    app, client
):
    api = provider(app)
    data = dict(
        movies=[
            dict(
                tmdb_id=32055,
                title="The Chaos Class",
                overview="English synopsis",
                poster_url=None,
                year=1975,
                score_percent=82,
            )
        ],
        waiting=[],
        errors=[],
        profile={"ready": True},
    )
    original = copy.deepcopy(data)
    app.extensions["recommender"].recommend = Mock(return_value=data)
    for language in ("tr", "en", "tr"):
        post(client, "/settings/language", language=language)
        html = client.get("/api/recommendations").json["html"]
        assert ("Hababam Sınıfı" if language == "tr" else "The Chaos Class") in html
        assert 'name="movie_id" value="32055"' in html
    assert data == original and api.call_count == 1


def test_schema_v2_upgrade_backs_up_every_user_field_without_changing_rows(tmp_path):
    path = tmp_path / "v2.db"
    db = Database(path)
    db.migrate()
    db.add_tmdb(
        dict(
            tmdb_id=32055, title="The Chaos Class", note="Keep it", rating=9, favorite=1
        )
    )
    db.execute("INSERT INTO settings(key,value) VALUES('ui_language','tr')")
    before = db.query("SELECT * FROM movies")
    with sqlite3.connect(path) as con:
        con.execute("DROP TABLE movie_metadata")
        con.execute("PRAGMA user_version=2")
    db.migrate()
    assert db.query("SELECT * FROM movies") == before
    assert db.query("SELECT value FROM settings WHERE key='ui_language'") == [
        {"value": "tr"}
    ]
    assert db.query("PRAGMA user_version")[0]["user_version"] == 4
    backup = list(tmp_path.glob("*.before-v4-*.bak"))
    assert len(backup) == 1
    assert Database(backup[0]).query("SELECT * FROM movies") == before
    db.migrate()
    assert len(list(tmp_path.glob("*.bak"))) == 1


def test_damaged_cache_cannot_redirect_a_library_movie_to_another_id(app, client):
    provider(app)
    post(client, "/add_from_catalog", movie_id=32055)
    db = app.extensions["db"]
    row = db.movie(1)
    payload = json.loads(
        db.query("SELECT data_json FROM movie_metadata")[0]["data_json"]
    )
    payload["details"]["tmdb_id"] = 999
    payload["details"]["title"] = "Wrong movie"
    db.execute("UPDATE movie_metadata SET data_json=?", json.dumps(payload))
    app.extensions["tmdb"].get = Mock(side_effect=TMDBError("Offline"))
    html = client.get("/movie/1").get_data(as_text=True)
    assert "Wrong movie" not in html and "The Chaos Class" in html
    assert db.movie(1) == row
