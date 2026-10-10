"""Recognizable discoveries, bounded cast signals and persistent portrait upgrades."""

import json
from datetime import date, timedelta
from unittest.mock import Mock

import pytest
from test_app import post
from test_catalog import provider, turkish_movie
from test_recommendation_model import rich
from test_recommendations import mock_recommendations

from recommendation_model import build_profile, rank_candidates, recognition_signals
from recommendations import Recommender
from tmdb_client import (
    RECOMMENDATION_FEATURES_VERSION,
    TMDBError,
    image_url,
    movie_details,
)


def taste():
    return build_profile([rich(i, rating=9) for i in range(1, 20)])


def classic(mid, genres=(53,)):
    return dict(
        rich(mid, genres), release_date="1995-05-01", vote_count=30000, vote_average=8.2
    )


@pytest.mark.parametrize("mode", ["familiar", "balanced", "explore"])
def test_acclaimed_recognizable_classic_beats_tiny_sample_high_rating(mode):
    obscure = dict(classic(100), vote_count=60, vote_average=9.5)
    known = classic(101)
    picks = rank_candidates([obscure, known], taste(), mode=mode, limit=1)
    assert picks[0]["tmdb_id"] == 101
    assert picks[0]["genre_ids"] == [53]
    assert picks[0]["recommendation_highlight"] == "Acclaimed classic"
    assert not rank_candidates([known], taste(), excluded={101})


def test_popular_classic_does_not_override_taste_or_repeated_dislikes():
    known = classic(100, (27,))
    matched = dict(rich(101), vote_count=500, vote_average=7.7)
    profile = build_profile(
        [rich(i, rating=9) for i in range(1, 20)]
        + [rich(i, (27,), rating=2) for i in range(20, 32)]
    )
    picks = rank_candidates([known, matched], profile, mode="familiar")
    assert [p["tmdb_id"] for p in picks] == [101]


@pytest.mark.parametrize(
    "change",
    [
        {"vote_count": 90},
        {"vote_average": 6.3},
        {"release_date": date.today().isoformat()},
        {"release_date": ""},
    ],
)
def test_old_or_popular_alone_does_not_mean_classic(change):
    raw = dict(classic(100), **change)
    assert recognition_signals(raw, 0.8)["classic"] is False


def recent(mid, popularity=0, score=7.8):
    raw = dict(
        rich(mid, cast=(900,)),
        release_date=(date.today() - timedelta(days=60)).isoformat(),
        vote_count=500,
        vote_average=score,
    )
    raw["entities"]["cast"][0]["popularity"] = popularity
    return raw


def test_recent_well_received_lead_cast_is_a_bounded_advantage():
    known, unknown = recent(101, 100), recent(100, 1)
    assert rank_candidates([unknown, known], taste(), limit=1)[0]["tmdb_id"] == 101
    bad = recent(102, 100, score=4)
    assert rank_candidates([bad, unknown], taste(), limit=1)[0]["tmdb_id"] == 100
    assert recognition_signals(bad, 0.5)["bonus"] == 0
    assert recognition_signals(known, 0.8)["bonus"] < 0.33


def test_minor_credit_and_old_cast_popularity_do_not_supply_new_movie_bonus():
    raw = recent(100)
    raw["entities"]["cast"] = [{"id": i, "popularity": 0} for i in range(4)]
    base = recognition_signals(raw, 0.8)["bonus"]
    raw["entities"]["cast"][3]["popularity"] = 1000000
    assert recognition_signals(raw, 0.8)["bonus"] == base
    old = dict(raw, release_date="1995-05-01")
    raw["entities"]["cast"][0]["popularity"] = 1000000
    assert recognition_signals(old, 0.8)["bonus"] == base


@pytest.mark.parametrize(
    "popularity", [None, "100", True, -8, float("nan"), float("inf")]
)
def test_invalid_optional_popularity_is_neutral(popularity):
    raw = recent(100, popularity)
    assert recognition_signals(raw, 0.8) == recognition_signals(recent(100), 0.8)


def test_classic_source_covers_all_genres_and_uses_existing_gateway_filters(app):
    calls = mock_recommendations(app)
    app.extensions["recommender"].recommend()
    sources = [p for path, p in calls if path == "discover/movie"]
    assert len(sources) == 10  # No extra provider calls for genre/recognition evidence.
    classics = [p for p in sources if p.get("vote_count.gte") == 1000]
    assert len(classics) == 1
    assert "with_genres" not in classics[0]
    assert "vote_average.gte" not in classics[0]  # Not enabled in the deployed proxy.
    assert classics[0]["primary_release_date.lte"].startswith(
        str(date.today().year - 10)
    )


def test_previous_public_cache_still_provides_offline_picks_after_upgrade(app):
    db = app.extensions["db"]
    db.execute(
        "INSERT OR REPLACE INTO settings VALUES(?,?)",
        "recommendation_public_catalog_v2",
        json.dumps({"version": "2", "movies": [classic(i) for i in range(100, 120)]}),
    )
    db.add_tmdb(dict(tmdb_id=100, title="Private library", note="Keep this", rating=9))
    before = db.query("SELECT * FROM movies")
    app.extensions["tmdb"].get = Mock(side_effect=TMDBError("Offline"))
    result = Recommender(db, app.extensions["tmdb"]).recommend()
    assert len(result["movies"]) == 10
    assert 100 not in [m["tmdb_id"] for m in result["movies"]]
    assert db.query("SELECT * FROM movies") == before


def test_unavailable_portrait_upgrades_stop_after_one_optional_batch(app):
    db, catalog = app.extensions["db"], app.extensions["catalog"]
    for mid in range(100, 124):
        provider(app, turkish_movie(mid))
        catalog.details(mid)
    for row in db.query("SELECT tmdb_id,data_json FROM movie_metadata"):
        payload = json.loads(row["data_json"])
        payload["details"]["recommendation_features_version"] = 1
        db.execute(
            "UPDATE movie_metadata SET data_json=? WHERE tmdb_id=?",
            json.dumps(payload),
            row["tmdb_id"],
        )
    api = Mock(side_effect=TMDBError("Offline"))
    app.extensions["tmdb"].get = api
    enriched = app.extensions["recommender"].enrich_candidates(
        {mid: recent(mid) for mid in range(100, 124)}
    )
    assert api.call_count == 4
    assert len(enriched) == 24 and all(m["entities"]["cast"] for m in enriched.values())


def test_recommendation_tags_translate_without_changing_selection(app, client):
    service = app.extensions["recommender"]
    payload = dict(
        movies=rank_candidates([classic(101, (80, 53, 878))], taste()),
        waiting=[],
        profile=taste(),
        errors=[],
    )
    service.recommend = Mock(return_value=payload)
    post(client, "/settings/language", language="en")
    english = client.get("/api/recommendations").json["html"]
    post(client, "/settings/language", language="tr")
    turkish = client.get("/api/recommendations").json["html"]
    assert all(label in english for label in ("Crime", "Thriller", "Science Fiction"))
    assert all(label in turkish for label in ("Suç", "Gerilim", "Bilim kurgu"))
    assert "Beğenilen klasik" in turkish
    assert 'data-tmdb-id="101"' in english and 'data-tmdb-id="101"' in turkish
    assert payload["movies"][0]["genre_ids"] == [80, 53, 878]


def portraits():
    raw = turkish_movie()
    raw["credits"]["cast"][0].update(profile_path="/actor_A.jpg", popularity=55)
    raw["credits"]["crew"][0].update(profile_path="/director_B.png", popularity=12)
    return raw


def test_portraits_save_on_add_for_library_and_unsaved_preview(app, client):
    api = provider(app, portraits())
    preview = client.get("/catalog_movie/32055")
    assert preview.status_code == 200
    assert (
        b"/w185/actor_A.jpg" in preview.data and b"/w185/director_B.png" in preview.data
    )
    mid = post(client, "/add_from_catalog", movie_id=32055).json["id"]
    assert api.call_count == 1
    saved = app.extensions["db"].movie(mid)
    credits = json.loads(saved["entities_json"])
    assert credits["cast"][0]["portrait_url"].endswith("/w185/actor_A.jpg")
    assert credits["directors"][0]["portrait_url"].endswith("/w185/director_B.png")
    api.side_effect = TMDBError("Offline")
    page = client.get(f"/movie/{mid}").get_data(as_text=True)
    assert 'aria-label="Actor 0"' in page and 'class="portrait-placeholder"' in page
    assert "/explore/person/300" in page and "/explore/person/100" in page
    assert api.call_count == 1 and app.extensions["db"].movie(mid) == saved


def downgrade(app):
    db = app.extensions["db"]
    cache = json.loads(db.query("SELECT data_json FROM movie_metadata")[0]["data_json"])
    cache["details"]["recommendation_features_version"] = 1
    for group in ("cast", "directors", "writers", "producers"):
        for person in cache["details"]["entities"][group]:
            person.pop("portrait_url", None)
            person.pop("popularity", None)
    db.execute("UPDATE movie_metadata SET data_json=?", json.dumps(cache))
    db.execute(
        "UPDATE movies SET entities_json=?", json.dumps(cache["details"]["entities"])
    )


def test_existing_same_length_cast_upgrades_once_by_id_keeps_personal_fields(
    app, client
):
    api = provider(app, portraits())
    post(client, "/add_from_catalog", movie_id=32055)
    post(
        client,
        "/edit/1",
        note="Özel yorumum",
        rating="9",
        favorite="1",
        watched_date="2021-04-05",
    )
    downgrade(app)
    db = app.extensions["db"]
    before = db.movie(1)
    for _ in range(2):
        page = client.get("/movie/1").get_data(as_text=True)
        assert "/w185/actor_A.jpg" in page
    after = db.movie(1)
    assert {k: v for k, v in after.items() if k != "entities_json"} == {
        k: v for k, v in before.items() if k != "entities_json"
    }
    assert len(json.loads(after["entities_json"])["cast"]) == 15
    assert api.call_count == 2


def test_failed_optional_portrait_upgrade_keeps_cache_and_does_not_retry_each_read(
    app, client
):
    api = provider(app, portraits())
    post(client, "/add_from_catalog", movie_id=32055)
    downgrade(app)
    before = app.extensions["db"].query("SELECT * FROM movie_metadata")
    api.side_effect = TMDBError("Offline")
    for _ in range(2):
        page = client.get("/movie/1").get_data(as_text=True)
        assert "Actor 14" in page and "okul maceraları" not in page
    assert api.call_count == 2
    assert app.extensions["db"].query("SELECT * FROM movie_metadata") == before


@pytest.mark.parametrize(
    "path",
    [
        None,
        123,
        {},
        "//example.com/photo.jpg",
        "https://example.com/a.jpg",
        "/../a.jpg",
        "/a.jpg?token=x",
    ],
)
def test_invalid_portrait_paths_are_safe_local_fallbacks(path):
    raw = portraits()
    raw["credits"]["cast"][0]["profile_path"] = path
    raw["credits"]["cast"][0]["popularity"] = float("nan")
    details = movie_details(raw)
    assert details["entities"]["cast"][0]["portrait_url"] is None
    assert details["entities"]["cast"][0]["popularity"] == 0
    assert image_url(path) is None
    assert details["recommendation_features_version"] == RECOMMENDATION_FEATURES_VERSION
