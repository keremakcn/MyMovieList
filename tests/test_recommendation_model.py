"""Content preference, calibration, privacy and cache regression scenarios."""

import copy
import json

import pytest
from test_app import MOVIE, post
from test_recommendations import candidate, mock_recommendations, row

from recommendation_model import (
    build_profile,
    movie_features,
    profile_fingerprint,
    rank_candidates,
    score_features,
)
from recommendations import PUBLIC_CACHE_KEY, Recommender
from tmdb_client import TMDBError


def rich(
    mid,
    genres=(53,),
    *,
    director=None,
    cast=(),
    keywords=(),
    collection=None,
    rating=None,
):
    movie = candidate(mid, genres[0])
    movie.update(
        tmdb_id=mid,
        genre_ids=list(genres),
        rating=rating,
        favorite=0,
        keyword_ids=list(keywords),
        collection_id=collection,
        entities={
            "directors": [{"id": director, "name": "Director"}] if director else [],
            "cast": [{"id": pid, "name": "Actor"} for pid in cast],
        },
    )
    return movie


@pytest.mark.parametrize("feature", ["director", "cast", "keywords"])
def test_rich_features_distinguish_movies_in_the_same_genre(feature):
    value = 901 if feature == "director" else (901,)
    library = [rich(i, rating=9, **{feature: value}) for i in range(1, 20)]
    profile = build_profile(library)
    matched = rich(100, **{feature: value})
    other = rich(101, **{feature: 902 if feature == "director" else (902,)})
    assert (
        score_features(movie_features(matched), profile)["fit"]
        > score_features(movie_features(other), profile)["fit"]
    )
    assert (
        rank_candidates([other, matched], profile, mode="familiar", limit=1)[0][
            "tmdb_id"
        ]
        == 100
    )


def test_language_titles_notes_and_order_never_change_profile_identity():
    library = [
        rich(i, rating=9, director=i + 200, keywords=(101,)) for i in range(1, 12)
    ]
    changed = copy.deepcopy(library)
    for movie in changed:
        movie.update(
            title="Türkçe başlık",
            original_title="Changed display title",
            note="Ignored private note",
        )
    assert profile_fingerprint(build_profile(library)) == profile_fingerprint(
        build_profile(changed[::-1])
    )
    pool = [rich(i, keywords=(101,)) for i in range(100, 130)]
    ids = lambda p: [m["tmdb_id"] for m in p]
    assert ids(rank_candidates(pool, build_profile(library), seed="fixed")) == ids(
        rank_candidates(pool, build_profile(changed), seed="fixed")
    )


def test_unrated_watchlist_is_not_positive_evidence_and_moderate_ratings_can_be_ready():
    assert build_profile([row(i) for i in range(100)])["count"] == 0
    assert build_profile([row(i, rating=7) for i in range(100)])["ready"]
    assert not build_profile([row(1, rating=10)])["ready"]


def test_lead_cast_limit_prevents_minor_credits_from_dominating_taste():
    movie = rich(1, cast=tuple(range(1, 60)), rating=9)
    assert movie_features(movie)["cast"] == frozenset(range(1, 7))
    assert 59 not in build_profile([movie])["features"]["cast"]


def test_single_twist_like_does_not_dominate_but_consistent_twist_taste_matters():
    sparse = [rich(1, rating=10, keywords=(999,))] + [
        rich(i, rating=9, keywords=(i,)) for i in range(2, 31)
    ]
    devoted = [rich(i, rating=9, keywords=(999,)) for i in range(1, 101)]
    pool = [rich(i, keywords=(999,)) for i in range(1000, 1040)] + [
        rich(i, keywords=(i,)) for i in range(2000, 2040)
    ]
    picks = rank_candidates(pool, build_profile(sparse), mode="familiar")
    assert sum(p["tmdb_id"] < 2000 for p in picks) <= 2
    assert (
        sum(
            p["tmdb_id"] < 2000
            for p in rank_candidates(pool, build_profile(devoted), mode="familiar")
        )
        >= 7
    )


def test_secondary_interests_survive_a_stronger_main_interest():
    library = [rich(i, (878,), rating=9) for i in range(1, 31)] + [
        rich(i, (35,), rating=9) for i in range(31, 41)
    ]
    pool = (
        [rich(i, (878,)) for i in range(100, 160)]
        + [rich(i, (35,)) for i in range(200, 260)]
        + [rich(i, (99,)) for i in range(300, 360)]
    )
    ids = [
        m["tmdb_id"]
        for m in rank_candidates(pool, build_profile(library), mode="familiar")
    ]
    assert 1 <= sum(200 <= i < 260 for i in ids) <= 3
    assert sum(100 <= i < 160 for i in ids) >= 5
    assert sum(i >= 300 for i in ids) == 2


def test_modes_discover_different_themes_even_within_the_same_genre():
    profile = build_profile([rich(i, rating=9, keywords=(999,)) for i in range(1, 101)])
    pool = [rich(i, keywords=(999,)) for i in range(1000, 1060)] + [
        rich(i, keywords=(i,)) for i in range(2000, 2060)
    ]
    mixes = {
        mode: sum(
            p["tmdb_id"] < 2000 for p in rank_candidates(pool, profile, mode=mode)
        )
        for mode in ("familiar", "balanced", "explore")
    }
    assert mixes == {"familiar": 8, "balanced": 5, "explore": 2}


def test_franchise_and_director_caps_relax_only_when_alternatives_are_exhausted():
    profile = build_profile([rich(i, rating=9) for i in range(1, 20)])
    pool = [rich(i, collection=77, director=88) for i in range(100, 120)] + [
        rich(i, director=i) for i in range(200, 220)
    ]
    ids = [m["tmdb_id"] for m in rank_candidates(pool, profile, mode="familiar")]
    assert sum(i < 200 for i in ids) <= 1
    assert len(rank_candidates(pool[:4], profile)) == 4


def test_one_dislike_is_not_genre_ban_repeated_negative_evidence_is():
    pool = [candidate(100, 27)]
    assert rank_candidates(pool, build_profile([row(1, "Horror", rating=2)]))
    assert not rank_candidates(
        pool, build_profile([row(i, "Horror", rating=2) for i in range(20)])
    )


def test_adult_future_duplicate_and_invalid_public_records_are_excluded():
    invalid = [
        dict(candidate(1), id=True),
        dict(candidate(2), vote_average="bad"),
        dict(candidate(3), vote_count=-1),
        dict(candidate(4), adult=True),
        dict(candidate(5), release_date="2999-01-01"),
        dict(candidate(6), release_date="2020-02-31"),
    ]
    pool = invalid + [candidate(100), candidate(100), candidate(101)]
    assert [
        m["tmdb_id"] for m in rank_candidates(pool, build_profile([]), excluded={101})
    ] == [100]
    assert (
        movie_features(dict(candidate(200), keyword_ids=42, entities={"cast": 42}))[
            "keywords"
        ]
        == frozenset()
    )


def test_profile_changes_keep_cards_stable_then_refresh_applies_feedback(app, client):
    mock_recommendations(app)
    service = app.extensions["recommender"]
    first = service.recommend()
    app.extensions["db"].add_tmdb(
        dict(
            tmdb_id=999999, title="Private", rating=9, genre="Comedy", status="Watched"
        )
    )
    changed = service.recommend()
    assert changed["movies"] == first["movies"] and changed["profile_changed"]
    assert "Your taste has changed" in client.get("/api/recommendations").json["html"]
    refreshed = post(client, "/api/recommendations/refresh")
    assert refreshed.status_code == 200 and not refreshed.json["profile_changed"]
    assert service.recommend()["profile"]["count"] == 1


def test_saved_public_pool_survives_restart_offline_and_excludes_library(app):
    calls = mock_recommendations(app)
    service = app.extensions["recommender"]
    first = service.recommend()["movies"]
    added = first[0]["tmdb_id"]
    app.extensions["db"].add_tmdb(
        dict(tmdb_id=added, title="Personal", note="Private", status="Watchlist")
    )
    calls.clear()
    app.extensions["tmdb"].get = lambda *a, **k: (_ for _ in ()).throw(
        TMDBError("Offline")
    )
    reopened = Recommender(app.extensions["db"], app.extensions["tmdb"])
    picks = reopened.recommend()
    assert len(picks["movies"]) == 10 and not picks["errors"] and not calls
    assert added not in [m["tmdb_id"] for m in picks["movies"]]
    saved = app.extensions["db"].query(
        "SELECT value FROM settings WHERE key=?", PUBLIC_CACHE_KEY
    )[0]["value"]
    assert "Private" not in saved and "Personal" not in saved and "rating" not in saved


def test_detail_outage_stops_optional_batches_and_keeps_genre_recommendations(app):
    calls = mock_recommendations(app)
    get = app.extensions["tmdb"].get

    def fail_details(path, **params):
        if path.startswith("movie/"):
            calls.append((path, params))
            raise TMDBError("Optional details offline")
        return get(path, **params)

    app.extensions["tmdb"].get = fail_details
    data = app.extensions["recommender"].recommend()
    assert len(data["movies"]) == 10 and not data["errors"]
    assert len([p for p, _ in calls if p.startswith("movie/")]) == 4


def test_exhausted_reserve_refills_without_moving_remaining_visible_cards(app):
    service = app.extensions["recommender"]
    pool = {i: candidate(i) for i in range(100, 200)}
    service.candidate_pool = lambda **_: (pool, [])
    service.recommend()
    reserved = list(service.session_picks["balanced"])
    db = app.extensions["db"]
    for movie in reserved[:-2]:
        db.execute(
            "INSERT INTO recommendation_dismissals VALUES(?,?,?)",
            movie["tmdb_id"],
            "Hidden",
            "now",
        )
    next_picks = service.recommend()["movies"]
    assert len(next_picks) == 10
    assert next_picks[:2] == reserved[-2:]
    assert len({m["tmdb_id"] for m in next_picks}) == 10


@pytest.mark.parametrize(
    "payload",
    [
        "broken json",
        "[]",
        json.dumps(
            {
                "version": "2",
                "movies": [
                    dict(candidate(1), vote_average="bad"),
                    dict(candidate(2), id=True),
                ],
            }
        ),
    ],
)
def test_damaged_public_cache_does_not_break_library_or_recommendations(app, payload):
    db = app.extensions["db"]
    mid, _ = db.add_tmdb(
        dict(tmdb_id=555, title="Safe", note="Keep", rating=8, favorite=1)
    )
    before = db.movie(mid)
    db.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", PUBLIC_CACHE_KEY, payload)
    service = Recommender(db, app.extensions["tmdb"])
    assert not service.public_pool and db.movie(mid) == before


def test_keywords_metadata_is_verified_and_saved_without_mutating_personal_data(app):
    db = app.extensions["db"]
    mid, _ = db.add_tmdb(
        dict(tmdb_id=603, title="Original", note="Keep", rating=9, favorite=1)
    )
    before = db.movie(mid)
    catalog = app.extensions["catalog"]
    app.extensions["tmdb"].get = lambda *a, **k: dict(
        MOVIE,
        keywords={"id": 603, "keywords": [{"id": 101, "name": "twist"}]},
        belongs_to_collection={"id": 20},
    )
    details = catalog.details(603, features=True)
    assert details["keyword_ids"] == [101] and details["collection_id"] == 20
    profile = build_profile(app.extensions["recommender"].library())
    assert profile["features"]["keywords"][101] > 0
    assert db.movie(mid) == before


@pytest.mark.parametrize(
    "keywords",
    [
        {"id": 999, "keywords": []},
        {"keywords": [{"id": True}]},
        {"keywords": "invalid"},
    ],
)
def test_invalid_keyword_metadata_is_not_cached(app, keywords):
    catalog = app.extensions["catalog"]
    app.extensions["tmdb"].get = lambda *a, **k: dict(MOVIE, keywords=keywords)
    with pytest.raises(TMDBError):
        catalog.details(603, features=True)
    assert not catalog.cached([603])
