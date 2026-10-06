"""Regression checks for taste onboarding and local ranking."""

from concurrent.futures import ThreadPoolExecutor
import sqlite3
from test_app import post, MOVIE
from recommendations import Recommender, build_profile, rank_candidates
from storage import Database
from tmdb_client import TMDBError


def row(i, genre="Thriller", rating=None, favorite=0, liked=0, director=None):
    return dict(
        id=i,
        tmdb_id=i,
        title=f"Liked {i}",
        genre=genre,
        rating=rating,
        favorite=favorite,
        survey_liked=liked,
        director=director,
    )


def candidate(i, genre=53):
    return dict(
        id=i,
        title=f"Candidate {i}",
        genre_ids=[genre],
        vote_average=7.5,
        vote_count=300,
        release_date="2020-01-01",
        poster_path=None,
    )


def mock_recommendations(app):
    calls = []

    def get(path, **params):
        calls.append((path, params))
        if path.startswith("movie/"):
            mid = int(path.split("/")[1])
            return dict(
                MOVIE, id=mid, title=f"Film {mid}",
                credits={"cast": [{"id": mid + 100000, "name": f"Actor {mid}"}],
                         "crew": [{"id": mid + 200000, "name": f"Director {mid}", "job": "Director"}]},
                keywords={"keywords": []},
            )
        if path == "discover/movie":
            genre = int(str(params["with_genres"]).split("|")[0])
            return dict(
                results=[
                    candidate(genre * 100 + params.get("page", 1) * 10 + i, genre)
                    for i in range(20)
                ],
                total_pages=20,
            )
        if path == "search/movie":
            return dict(results=[candidate(111), candidate(112)], total_pages=2)
        raise AssertionError(path)

    app.extensions["tmdb"].get = get
    return calls


def test_single_rating_is_weak_but_consistent_pattern_is_stronger():
    weak = build_profile([row(1, rating=10)])
    strong = build_profile([row(i, rating=10) for i in range(100)])
    assert weak["affinities"][53] < 0.25 and weak["confidence"] < 0.2
    assert strong["affinities"][53] > 0.6 and strong["ready"]
    related = build_profile(
        [row(i, rating=10, director="Same director") for i in range(10)]
    )
    diverse = build_profile(
        [row(i, rating=10, director=f"Director {i}") for i in range(10)]
    )
    assert related["confidence"] < diverse["confidence"]
    assert build_profile([row(1)])["count"] == 0


def test_negative_feedback_and_explicit_rating_override_survey():
    profile = build_profile([row(1, rating=2, favorite=1, liked=1)])
    assert profile["affinities"][53] < 0
    picks = rank_candidates([candidate(100, 53), candidate(101, 35)], profile, limit=1)
    assert picks[0]["tmdb_id"] == 101
    assert build_profile([row(1, liked=1)])["affinities"][53] > 0


def test_ranking_is_diverse_excludes_seen_and_deduplicates():
    profile = build_profile([row(1, rating=10)])
    pool = [candidate(i) for i in range(100, 115)] + [
        candidate(200, 35),
        candidate(201, 16),
        candidate(202, 18),
    ]
    picks = rank_candidates(pool + pool, profile, excluded={100}, limit=6)
    ids = [p["tmdb_id"] for p in picks]
    assert len(ids) == len(set(ids)) == 6 and 100 not in ids
    assert len(set(ids) & {200, 201, 202}) >= 2
    assert any("Liked 1" in p["reason"] for p in picks)


def test_survey_is_atomic_idempotent_and_preserves_existing_metadata(app, client):
    mock_recommendations(app)
    db = app.extensions["db"]
    mid, _ = db.add_tmdb(
        dict(
            tmdb_id=603,
            title="Original",
            status="Watchlist",
            note="Keep me",
            rating=8,
            favorite=1,
            watched_date="2020-01-01",
        )
    )
    before = db.movie(mid)
    response = post(
        client, "/taste/save", movie_id=["603", "111", "111"], mode="balanced"
    )
    assert response.status_code == 200 and response.json["created"] == 1
    assert db.movie(mid) == before
    new = db.query("SELECT * FROM movies WHERE tmdb_id=111")[0]
    assert new["status"] == "Watched" and new["rating"] is None and new["favorite"] == 0
    assert new["watched_date"] is None
    assert len(db.query("SELECT * FROM recommendation_likes")) == 2
    assert (
        post(client, "/taste/save", movie_id=["603", "111"], mode="balanced").json[
            "created"
        ]
        == 0
    )
    assert len(db.query("SELECT * FROM movies")) == 2
    assert b"Original" in client.get("/taste").data
    post(client, "/taste/save", movie_id=["111"], mode="balanced")
    assert db.movie(mid) == before  # Removing a survey choice never removes the film.
    assert len(db.query("SELECT * FROM recommendation_likes")) == 1


def test_survey_failure_keeps_all_previous_state(app, client):
    mock_recommendations(app)
    post(client, "/taste/save", movie_id=["111"], mode="balanced")
    db = app.extensions["db"]
    original = app.extensions["tmdb"].get

    def fail(path, **params):
        if path == "movie/333":
            raise TMDBError("Offline")
        return original(path, **params)

    app.extensions["tmdb"].get = fail
    response = post(client, "/taste/save", movie_id=["222", "333"], mode="explore")
    assert response.status_code == 502
    assert [r["tmdb_id"] for r in db.query("SELECT tmdb_id FROM movies")] == [111]
    assert (
        db.query("SELECT value FROM settings WHERE key=?", "recommendation_mode")[0][
            "value"
        ]
        == "balanced"
    )


def test_parallel_survey_and_add_never_duplicate(app):
    db = app.extensions["db"]
    entries = [(100, dict(title="One film", genre="Drama"))]

    def add(_):
        db.save_survey(entries, "balanced")

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(add, range(8)))
    assert len(db.query("SELECT * FROM movies")) == 1
    assert len(db.query("SELECT * FROM recommendation_likes")) == 1


def test_candidates_do_not_transmit_personal_preferences(app, tmp_path):
    calls = mock_recommendations(app)
    service = app.extensions["recommender"]
    service.recommend()
    initial = sorted((path, str(sorted(params.items()))) for path, params in calls)
    from app import create_app
    folder = tmp_path / "second-device"
    other = create_app(dict(TESTING=True, SECRET_KEY="test", DATA_DIR=str(folder),
                            DATABASE=str(folder / "library.db"), UI_LANGUAGE_DETECTOR=lambda: "en"))
    other_calls = mock_recommendations(other)
    other.extensions["db"].add_tmdb(
        dict(
            tmdb_id=999,
            title="Private selection",
            genre="Horror",
            status="Watched",
            rating=10,
            favorite=1,
            note="Private note",
        )
    )
    other.extensions["recommender"].recommend()
    assert (
        sorted((path, str(sorted(params.items()))) for path, params in other_calls) == initial
    )
    assert all(path != "movie/999" for path, _ in other_calls)
    assert all("Private" not in str(params) for _, params in other_calls)


def test_recommendation_endpoints_dismiss_restore_and_waiting(app, client):
    mock_recommendations(app)
    db = app.extensions["db"]
    db.add_tmdb(
        dict(
            tmdb_id=2810,
            title="Already watched",
            status="Watched",
            genre="Action",
            rating=9,
        )
    )
    db.add_tmdb(
        dict(
            tmdb_id=2811, title="Saved for tonight", status="Watchlist", genre="Action"
        )
    )
    assert client.get("/recommendations").status_code == 200
    response = client.get("/api/recommendations")
    assert response.status_code == 200
    html = response.json["html"]
    assert "/catalog_movie/2810" not in html and "/catalog_movie/2811" not in html
    assert "Saved for tonight" in html and "back=/recommendations" in html
    picks = app.extensions["recommender"].recommend()["movies"]
    hidden = picks[0]["tmdb_id"]
    assert (
        post(
            client,
            "/recommendations/dismiss",
            movie_id=str(hidden),
            title="<script>bad</script>",
        ).status_code
        == 200
    )
    assert hidden not in [
        m["tmdb_id"] for m in app.extensions["recommender"].recommend()["movies"]
    ]
    assert b"&lt;script&gt;bad&lt;/script&gt;" in client.get("/recommendations").data
    assert (
        post(client, "/recommendations/restore", movie_id=str(hidden)).status_code
        == 302
    )
    assert not db.query("SELECT * FROM recommendation_dismissals")
    assert post(client, "/taste/skip").status_code == 302
    assert post(client, "/recommendations/mode", mode="explore").status_code == 302


def test_survey_choices_variety_search_and_validation(app, client):
    calls = mock_recommendations(app)
    response = client.get("/api/taste/choices").json
    assert len(response["movies"]) == 12
    assert len(set(p["tmdb_id"] for p in response["movies"])) == 12
    assert len(calls) == 6
    second = client.get("/api/taste/choices?page=2").json
    assert {m["tmdb_id"] for m in response["movies"]} != {
        m["tmdb_id"] for m in second["movies"]
    }
    assert len(client.get("/api/taste/choices?q=test").json["movies"]) == 2
    assert client.get("/api/taste/choices?page=bad").status_code == 400
    assert post(client, "/taste/save", movie_id=["-1"]).status_code == 400
    assert post(client, "/taste/save", movie_id=["1"], mode="bad").status_code == 400
    assert (
        post(client, "/taste/save", movie_id=[str(i) for i in range(1, 26)]).status_code
        == 400
    )
    assert client.post("/taste/save", data={"movie_id": "1"}).status_code == 400


def test_offline_suggestions_keep_local_watchlist(app, client):
    app.extensions["db"].add_tmdb(
        dict(tmdb_id=333, title="Local movie", status="Watchlist")
    )

    def fail(*args, **kwargs):
        raise TMDBError("Offline")

    app.extensions["tmdb"].get = fail
    response = client.get("/api/recommendations")
    assert response.status_code == 200
    assert "Offline" in response.json["html"] and "Local movie" in response.json["html"]
    assert client.get("/taste").status_code == 200


def test_v1_migration_backups_preserve_all_movie_data(tmp_path):
    path = tmp_path / "legacy.db"
    db = Database(path)
    db.migrate()
    mid, _ = db.add_tmdb(
        dict(tmdb_id=1, title="Saved", note="Keep", favorite=1, rating=9)
    )
    before = db.movie(mid)
    with sqlite3.connect(path) as con:
        con.execute("DROP TABLE recommendation_likes")
        con.execute("DROP TABLE recommendation_dismissals")
        con.execute("PRAGMA user_version=1")
    db.migrate()
    assert db.movie(mid) == before
    assert len(list(tmp_path.glob("*.before-v3-*.bak"))) == 1
    assert db.query("PRAGMA user_version")[0]["user_version"] == 3
    db.migrate()
    assert len(list(tmp_path.glob("*.bak"))) == 1


def test_profile_confidence_needs_consistency_and_is_order_independent():
    rows = [row(i, rating=10 if i % 2 else 2, director="Same") for i in range(20)]
    profile = build_profile(rows)
    reverse = build_profile(list(reversed(rows)))
    assert profile["confidence"] < 0.3
    assert not profile["ready"]
    assert abs(profile["affinities"][53] - reverse["affinities"][53]) < 1e-10


def test_session_picks_stable_across_requests_and_profile_changes(app):
    calls = mock_recommendations(app)
    service = app.extensions["recommender"]
    first = service.recommend()["movies"]
    assert len(first) == 10
    requests = len(calls)
    app.extensions["db"].add_tmdb(
        dict(
            tmdb_id=999999,
            title="Rated later",
            genre="Horror",
            rating=10,
            status="Watched",
        )
    )
    assert service.recommend()["movies"] == first
    assert len(calls) == requests
    reopened = Recommender(app.extensions["db"], app.extensions["tmdb"])
    second = reopened.recommend()["movies"]
    assert {m["tmdb_id"] for m in second} != {m["tmdb_id"] for m in first}
    assert reopened.recommend()["movies"] == second


def test_session_removes_added_or_hidden_without_reordering_other_picks(app):
    mock_recommendations(app)
    service = app.extensions["recommender"]
    first = service.recommend()["movies"]
    added, hidden = first[0]["tmdb_id"], first[1]["tmdb_id"]
    db = app.extensions["db"]
    db.add_tmdb(dict(tmdb_id=added, title="Saved", status="Watchlist"))
    db.execute(
        "INSERT INTO recommendation_dismissals VALUES (?,?,?)", hidden, "Hidden", "now"
    )
    next_ids = [m["tmdb_id"] for m in service.recommend()["movies"]]
    assert added not in next_ids and hidden not in next_ids
    assert next_ids[:8] == [m["tmdb_id"] for m in first[2:]]


def test_session_keeps_sparse_pool_available_and_retries_failed_fetch(app):
    mock_recommendations(app)
    service = app.extensions["recommender"]
    service.previous["balanced"] = {100, 101}
    service.candidate_pool = lambda **_: (
        {100: candidate(100), 101: candidate(101)},
        [],
    )
    assert len(service.recommend()["movies"]) == 2
    service.invalidate()
    service.candidate_pool = lambda **_: ({}, ["Offline"])
    assert service.recommend()["errors"] == ["Offline"]
    assert not service.session_picks
    service.candidate_pool = lambda **_: ({100: candidate(100)}, [])
    assert len(service.recommend()["movies"]) == 1


def test_restart_changes_picks_without_changing_preferences(app):
    mock_recommendations(app)
    first = app.extensions["recommender"].recommend()["movies"]
    second_service = Recommender(app.extensions["db"], app.extensions["tmdb"])
    second = second_service.recommend()["movies"]
    assert {m["tmdb_id"] for m in first} != {m["tmdb_id"] for m in second}
    assert second_service.recommend()["movies"] == second


def test_parallel_requests_share_one_session_selection(app):
    calls = mock_recommendations(app)
    service = app.extensions["recommender"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: service.recommend()["movies"], range(4)))
    assert all(result == results[0] for result in results)
    assert len([p for p, _ in calls if p == "discover/movie"]) == 10
    details = [p for p, _ in calls if p.startswith("movie/")]
    assert len(details) == len(set(details)) == 24


def test_manual_refresh_changes_only_selected_mode_and_keeps_exclusions(app, client):
    mock_recommendations(app)
    service = app.extensions["recommender"]
    first = service.recommend()["movies"]
    service.recommend("familiar")
    db = app.extensions["db"]
    added, hidden = first[0]["tmdb_id"], first[1]["tmdb_id"]
    db.add_tmdb(dict(tmdb_id=added, title="Saved", status="Watchlist"))
    db.execute(
        "INSERT INTO recommendation_dismissals VALUES (?,?,?)", hidden, "Hidden", "now"
    )
    familiar = service.recommend("familiar")["movies"]
    assert client.post("/api/recommendations/refresh").status_code == 400
    response = post(client, "/api/recommendations/refresh")
    assert response.status_code == 200
    second = service.recommend()["movies"]
    ids = {m["tmdb_id"] for m in second}
    assert added not in ids and hidden not in ids
    assert ids != {m["tmdb_id"] for m in first}
    assert service.recommend()["movies"] == second
    assert service.recommend("familiar")["movies"] == familiar
    assert "Why this film?" not in response.json["html"]


def test_failed_manual_refresh_preserves_current_selection(app):
    mock_recommendations(app)
    service = app.extensions["recommender"]
    first = service.recommend()["movies"]
    service.candidate_pool = lambda **_: ({}, ["Offline"])
    failed = service.recommend(refresh=True)
    assert failed["errors"] == ["Offline"]
    assert failed["movies"] == first
    assert service.recommend()["movies"] == first


def test_modes_have_distinct_familiar_discovery_mix():
    profile = build_profile(
        [row(i, rating=10) for i in range(30)]
        + [row(100 + i, genre="Horror", rating=2) for i in range(30)]
    )
    pool = (
        [candidate(1000 + i, 53) for i in range(60)]
        + [candidate(2000 + i, 35) for i in range(60)]
        + [candidate(3000 + i, 99) for i in range(60)]
        + [candidate(4000 + i, 27) for i in range(60)]
    )
    mixes = {}
    for mode in ("familiar", "balanced", "explore"):
        picks = rank_candidates(pool, profile, mode=mode, seed="fixed")
        ids = [m["tmdb_id"] for m in picks]
        mixes[mode] = sum(1000 <= mid < 2000 for mid in ids)
        assert not any(4000 <= mid < 5000 for mid in ids)
    assert mixes == {"familiar": 8, "balanced": 5, "explore": 2}


def test_repeated_refresh_does_not_cycle_between_recent_batches(app):
    service = app.extensions["recommender"]
    pool = {i: candidate(i, 53 if i % 2 else 35) for i in range(100, 200)}
    service.candidate_pool = lambda **_: (pool, [])
    seen = set()
    for batch in range(6):
        picks = service.recommend(refresh=batch > 0)["movies"]
        ids = {m["tmdb_id"] for m in picks}
        assert len(ids) == 10 and not seen.intersection(ids)
        seen.update(ids)
        assert service.recommend()["movies"] == picks
    import json

    history = json.loads(
        app.extensions["db"].query(
            "SELECT value FROM settings WHERE key='recommendation_last_picks'"
        )[0]["value"]
    )
    assert len(history["balanced"]) == 50
    reopened = Recommender(app.extensions["db"], app.extensions["tmdb"])
    reopened.candidate_pool = lambda **_: (pool, [])
    assert not set(history["balanced"]) & {
        m["tmdb_id"] for m in reopened.recommend()["movies"]
    }


def test_refresh_expands_public_pool_and_failed_fetch_does_not_advance(app):
    calls = mock_recommendations(app)
    service = app.extensions["recommender"]
    service.recommend()
    original_ids = set(service.public_pool)
    assert {params["page"] for path, params in calls if path == "discover/movie"} == {1}
    calls.clear()
    service.recommend("explore")
    assert not calls  # Modes reuse the same public pool.
    service.recommend(refresh=True)
    popular = [params for path, params in calls if path == "discover/movie" and params["sort_by"] == "popularity.desc"]
    assert len(popular) == 8 and {p["page"] for p in popular} == {2}
    world = [params for path, params in calls if path == "discover/movie" and "with_original_language" in params]
    assert world[0]["with_original_language"] == "ko" and world[0]["page"] == 1
    assert set(service.public_pool) > original_ids
    page = service.pool_page
    cached = dict(service.public_pool)

    def fail(*args, **kwargs):
        raise TMDBError("Offline")

    app.extensions["tmdb"].get = fail
    assert service.recommend(refresh=True)["errors"]
    assert service.pool_page == page and service.public_pool == cached


def test_small_pool_refresh_allows_repeats_without_duplicates(app):
    service = app.extensions["recommender"]
    service.candidate_pool = lambda **_: ({i: candidate(i) for i in range(10, 13)}, [])
    for _ in range(4):
        picks = service.recommend(refresh=True)["movies"]
        assert {m["tmdb_id"] for m in picks} == {10, 11, 12}
