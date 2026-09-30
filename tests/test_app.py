import re
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from app import safe_path
from storage import Database
from tmdb_client import TMDBClient, TMDBError


MOVIE = {
    "id": 603,
    "title": "The Matrix",
    "release_date": "1999-03-31",
    "poster_path": None,
    "overview": "A simulated reality.",
    "runtime": 136,
    "vote_average": 8.2,
    "vote_count": 100,
    "genres": [{"id": 1, "name": "Science Fiction"}],
    "credits": {
        "cast": [
            {
                "id": 6384,
                "name": "Keanu Reeves",
                "known_for_department": "Acting",
                "character": "Neo",
            }
        ],
        "crew": [{"id": 1, "name": "Lana Wachowski", "job": "Director"}],
    },
    "production_companies": [{"id": 174, "name": "Warner Bros."}],
}


def post(client, url, **values):
    client.get("/")
    with client.session_transaction() as session:
        token = session["csrf_token"]
    return client.post(
        url, data=values, headers={"X-CSRF-Token": token, "Accept": "application/json"}
    )


def mock_tmdb(app):
    def get(path, **params):
        if path.startswith("movie/"):
            return MOVIE
        if path.startswith("search/") or path == "discover/movie":
            if path == "search/person":
                results = [
                    {
                        "id": 6384,
                        "name": "Keanu Reeves",
                        "known_for_department": "Acting",
                        "known_for": [dict(MOVIE, media_type="movie")],
                    }
                ]
            elif path == "search/company":
                results = [{"id": 174, "name": "Warner Bros."}]
            else:
                results = [MOVIE, MOVIE]
            return {"results": results, "total_pages": 3, "total_results": 50}
        if path.startswith("person/"):
            return {
                "id": 6384,
                "name": "Keanu Reeves",
                "known_for_department": "Acting",
                "biography": "Actor.",
                "movie_credits": {"cast": [MOVIE], "crew": [MOVIE]},
            }
        return {"id": 174, "name": "Warner Bros.", "description": "Studio."}

    app.extensions["tmdb"].get = get


def test_pages_and_navigation(app, client):
    mock_tmdb(app)
    for path in [
        "/",
        "/search",
        "/search?q=matrix",
        "/search?q=keanu&type=person",
        "/search?q=warner&type=company",
        "/catalog_movie/603",
        "/explore/person/6384",
        "/settings",
        "/add",
    ]:
        response = client.get(path)
        assert response.status_code == 200, (path, response.data[:500])
        assert b"csrf-token" in response.data
    response = client.get("/catalog_movie/603")
    assert b"/explore/person/6384" in response.data
    assert b"/explore/company/174" in response.data
    assert client.get("/search?q=matrix").data.count(b'class="catalog-card"') == 1


def test_combined_search_and_typed_suggestions(app, client):
    mock_tmdb(app)
    html = client.get("/search?q=matrix").data
    for label in (
        b"The Matrix",
        b"Keanu Reeves",
        b"ACTOR",
        b"MOVIE",
        b"Actors",
    ):
        assert label in html
    assert b"Warner Bros." not in html
    assert b"Warner Bros." in client.get("/search?q=warner&type=company").data
    suggestions = client.get("/api/suggestions?q=ma").json["results"]
    assert [item["url"] for item in suggestions] == [
        "/catalog_movie/603",
        "/explore/person/6384",
    ]
    assert [item["subtitle"].split(" · ")[0] for item in suggestions] == [
        "Movie",
        "Actor",
    ]
    movie_only = client.get("/search?q=matrix&type=movie").data
    assert b"Keanu Reeves" not in movie_only and b"Warner Bros." not in movie_only
    actor_only = client.get("/search?q=keanu&type=person").data
    assert b"Keanu Reeves" in actor_only and b"ACTOR" in actor_only


def test_combined_search_keeps_successful_sources(app, client):
    mock_tmdb(app)
    original = app.extensions["tmdb"].get

    def partial(path, **params):
        if path == "search/person":
            raise TMDBError("Temporarily unavailable")
        return original(path, **params)

    app.extensions["tmdb"].get = partial
    html = client.get("/search?q=matrix").data
    assert b"The Matrix" in html and b"Keanu Reeves" not in html
    assert b"Actors &amp; Directors: Temporarily unavailable" in html
    assert b"1 matches on this page" in html


def test_combined_pagination_and_identity_are_per_type(app, client):
    calls = []

    def get(path, **params):
        calls.append((path, params["page"]))
        kind = path.split("/")[-1]
        rows = (
            [MOVIE]
            if kind == "movie"
            else [{"id": 603, "name": kind.title(), "known_for_department": "Acting"}]
        )
        return dict(
            results=rows,
            total_pages={"movie": 1, "person": 2, "company": 4}[kind],
            total_results=1,
        )

    app.extensions["tmdb"].get = get
    data = client.get("/api/suggestions?q=ab").json["results"]
    assert (
        len(data) == 2
    )  # Equal numeric IDs across different types are different entities.
    html = client.get("/search?q=ab&type=all&page=2").data
    assert b"Page 2 of 2" in html
    assert ("search/person", 2) in calls
    assert not any(path == "search/company" for path, page in calls)


def test_add_duplicate_remove_restore_preserves_every_column(app, client):
    mock_tmdb(app)
    first = post(client, "/add_from_catalog", movie_id=603).json
    movie_id = first["id"]
    assert first["created"]
    assert not post(client, "/add_from_catalog", movie_id=603).json["created"]
    post(
        client,
        f"/edit/{movie_id}",
        note="My long\nprivate note",
        rating="9",
        watched_date="2002-01-02",
    )
    post(client, f"/favorite/{movie_id}", value="1")
    before = app.extensions["db"].movie(movie_id)
    assert before["watched_date"] == "2002-01-02"
    assert before["status"] == "Watchlist"
    marker = post(client, f"/delete/{movie_id}").json["marker"]
    assert app.extensions["db"].movie(movie_id) is None
    assert b"The Matrix" not in client.get("/").data
    assert b"The Matrix" in client.get("/?status=trash").data
    assert post(client, f"/restore/{movie_id}", marker=marker).status_code == 200
    assert app.extensions["db"].movie(movie_id) == before
    assert post(client, f"/restore/{movie_id}", marker=marker).status_code == 200
    assert len(app.extensions["db"].query("SELECT * FROM movies")) == 1


def test_stale_undo_cannot_restore_later_deletion(app, client):
    mock_tmdb(app)
    movie_id = post(client, "/add_from_catalog", movie_id=603).json["id"]
    first = post(client, f"/delete/{movie_id}").json["marker"]
    post(client, f"/restore/{movie_id}", marker=first)
    second = post(client, f"/delete/{movie_id}").json["marker"]
    assert first != second
    assert post(client, f"/restore/{movie_id}", marker=first).status_code == 409
    assert app.extensions["db"].movie(movie_id) is None


def test_readding_removed_movie_restores_metadata(app, client):
    mock_tmdb(app)
    movie_id = post(client, "/add_from_catalog", movie_id=603).json["id"]
    post(client, f"/edit/{movie_id}", note="Keep me", rating="8")
    before = app.extensions["db"].movie(movie_id)
    post(client, f"/delete/{movie_id}")
    result = post(client, "/add_watched_from_catalog", movie_id=603).json
    assert result["id"] == movie_id
    assert app.extensions["db"].movie(movie_id) == before


def test_csrf_origin_and_safe_redirect(app, client):
    assert client.post("/add", data={"title": "Bad"}).status_code == 400
    client.get("/")
    with client.session_transaction() as session:
        token = session["csrf_token"]
    assert (
        client.post(
            "/add", headers={"X-CSRF-Token": token, "Origin": "https://evil.test"}
        ).status_code
        == 403
    )
    for value in ["//evil.test", "/\\evil.test", "https://evil.test", "/\nevil"]:
        assert safe_path(value) == "/"
    assert client.get("/", headers={"Host": "evil.test"}).status_code == 400


def test_validation_retains_input_and_escapes_html(app, client):
    response = post(
        client,
        "/add",
        title="<script>alert(1)</script>",
        rating="99",
        note="keep my draft",
    )
    assert response.status_code == 422
    assert b"keep my draft" in response.data
    assert b"&lt;script&gt;" in response.data
    assert not app.extensions["db"].query("SELECT * FROM movies")
    assert (
        post(client, "/add", title="Manual", status="Watched", rating=8).status_code
        == 302
    )
    row = app.extensions["db"].query("SELECT * FROM movies")[0]
    assert row["watched_date"] and row["created_at"]


def test_api_failure_not_reported_as_success(app, client):
    def failed(*args, **kwargs):
        raise TMDBError("Try again", 429)

    app.extensions["tmdb"].get = failed
    result = post(client, "/add_from_catalog", movie_id=603)
    assert result.status_code == 429 and result.json["error"] == "Try again"
    assert not app.extensions["db"].query("SELECT * FROM movies")
    assert b"Try again" in client.get("/search?q=matrix").data
    assert client.get("/api/suggestions?q=ma").status_code == 429


def test_suggestions_and_pagination(app, client):
    mock_tmdb(app)
    assert client.get("/api/suggestions?q=a").json == {"results": []}
    assert (
        client.get("/api/suggestions?q=ma").json["results"][0]["url"]
        == "/catalog_movie/603"
    )
    assert b"page=2" in client.get("/search?q=matrix").data
    assert client.get("/api/suggestions?q=ab&type=unknown").status_code == 400
    db = app.extensions["db"]
    for i in range(80):
        db.add_tmdb(dict(tmdb_id=i + 1, title=f"Movie {i:03}", status="Watchlist"))
    assert client.get("/").data.count(b'class="movie-card"') == 36
    assert b"Movie 001" in client.get("/?q=Movie+001").data
    assert client.get("/?page=999999").status_code == 200


def test_concurrent_add_and_restore(app):
    db = app.extensions["db"]
    values = dict(
        tmdb_id=603, title="The Matrix", status="Watchlist", note="original", rating=9
    )
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: db.add_tmdb(values), range(16)))
    assert len({r[0] for r in results}) == 1
    assert sum(r[1] for r in results) == 1
    movie_id = results[0][0]
    original = db.movie(movie_id)
    marker = db.remove(movie_id)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(
            pool.map(
                lambda n: (
                    db.restore(movie_id, marker) if n % 2 else db.add_tmdb(values)
                ),
                range(16),
            )
        )
    assert db.movie(movie_id) == original


def test_detail_edit_refresh_and_idempotent_actions(app, client):
    mock_tmdb(app)
    movie_id = post(client, "/add_watched_from_catalog", movie_id=603).json["id"]
    post(
        client,
        f"/edit/{movie_id}",
        rating="7",
        note="Personal",
        watched_date="2001-02-03",
    )
    for _ in range(2):
        post(client, f"/favorite/{movie_id}", value="1")
        post(client, f"/status/{movie_id}", value="Watched")
    row = app.extensions["db"].movie(movie_id)
    assert row["watched_date"] == "2001-02-03" and row["favorite"] == 1
    assert client.get(f"/movie/{movie_id}").status_code == 200
    assert client.get(f"/edit/{movie_id}").status_code == 200
    assert post(client, f"/movie/{movie_id}/refresh").status_code == 302
    refreshed = app.extensions["db"].movie(movie_id)
    for key in ("note", "rating", "watched_date", "favorite", "created_at", "id"):
        assert refreshed[key] == row[key]
    response = post(client, f"/edit/{movie_id}", rating="12", note="Draft preserved")
    assert response.status_code == 422 and b"Draft preserved" in response.data
    assert app.extensions["db"].movie(movie_id)["note"] == "Personal"


def test_restore_retains_rendered_sort_order(app, client):
    db = app.extensions["db"]
    ids = [
        db.add_tmdb(dict(tmdb_id=i, title=f"Title {i}", status="Watchlist", rating=i))[
            0
        ]
        for i in range(1, 5)
    ]
    for sort in ("", "added_asc", "added_desc", "rating_desc"):
        before = re.findall(
            rb'<article class="movie-card" data-movie-id="(\d+)"',
            client.get("/?sort=" + sort).data,
        )
        marker = post(client, f"/delete/{ids[1]}").json["marker"]
        post(client, f"/restore/{ids[1]}", marker=marker)
        after = re.findall(
            rb'<article class="movie-card" data-movie-id="(\d+)"',
            client.get("/?sort=" + sort).data,
        )
        assert before == after


def test_http_double_add_is_safe(app):
    mock_tmdb(app)

    def add(_):
        with app.test_client() as client:
            response = post(client, "/add_from_catalog", movie_id=603)
            assert response.status_code == 200
            return response.json["id"]

    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(add, range(8)))
    assert len(set(ids)) == 1


def test_settings_blank_does_not_remove_saved_token(app, client):
    post(client, "/settings", tmdb_token="example-token")
    post(client, "/settings", tmdb_token="")
    assert (
        app.extensions["db"].query("SELECT value FROM settings")[0]["value"]
        == "example-token"
    )
    assert b"example-token" not in client.get("/settings").data
    post(client, "/settings", clear_token="1")
    assert not app.extensions["db"].query("SELECT * FROM settings")


def test_rate_limit_cooldown_applies_to_different_requests():
    client = TMDBClient(lambda: "token")
    calls = []

    def limited(*args):
        calls.append(args)
        raise TMDBError("Slow down", 429, 60)

    client._request = limited
    with pytest.raises(TMDBError):
        client.get("search/movie", query="one")
    with pytest.raises(TMDBError) as exc:
        client.get("search/movie", query="two")
    assert exc.value.status == 429 and len(calls) == 1


def test_cache_single_flight_and_expiry():
    client = TMDBClient(lambda: "token", capacity=2)
    calls = []

    def fetch(*args):
        calls.append(args)
        time.sleep(0.02)
        return {"results": []}

    client._request = fetch
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: client.get("search/movie", query="matrix"), range(8)))
    assert len(calls) == 1
    client.get("movie/1")
    client.get("movie/2")
    assert len(client.cache) == 2

    def failed(*args):
        raise TMDBError("Offline")

    client._request = failed
    with pytest.raises(TMDBError):
        client.get("movie/3")
    key = next(reversed(client.cache))
    assert client.cache[key][0] - time.monotonic() < 4
    client.cache[key] = (0, client.cache[key][1])
    client._request = fetch
    assert client.get("movie/3") == {"results": []}


def test_migration_preserves_legacy_and_backs_up(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as con:
        con.execute(
            "CREATE TABLE movies(id INTEGER PRIMARY KEY, title TEXT, status TEXT, note TEXT, tmdb_id INTEGER, favorite INTEGER)"
        )
        con.execute("INSERT INTO movies VALUES(42,'Old','Watched','Keep',603,1)")
    db = Database(path)
    db.migrate()
    assert db.movie(42)["note"] == "Keep"
    assert db.movie(42)["created_at"] is None
    assert len(list(tmp_path.glob("*.bak"))) == 1
    db.migrate()
    assert len(list(tmp_path.glob("*.bak"))) == 1


def test_duplicate_migration_does_not_delete(tmp_path):
    path = tmp_path / "duplicates.db"
    with sqlite3.connect(path) as con:
        con.execute(
            "CREATE TABLE movies(id INTEGER PRIMARY KEY,title TEXT,tmdb_id INTEGER)"
        )
        con.executemany(
            "INSERT INTO movies VALUES(?,?,?)", [(1, "First", 42), (2, "Second", 42)]
        )
    with pytest.raises(RuntimeError, match="Duplicate"):
        Database(path).migrate()
    with sqlite3.connect(path) as con:
        assert con.execute("SELECT COUNT(*) FROM movies").fetchone()[0] == 2


def test_combined_actors_directors_and_profession_labels(app, client):
    mock_tmdb(app)
    original = app.extensions["tmdb"].get
    people = [
        {"id": 525, "name": "Christopher Nolan", "known_for_department": "Directing"},
        {"id": 138, "name": "Quentin Tarantino", "known_for_department": "Directing"},
        {"id": 6384, "name": "Keanu Reeves", "known_for_department": "Acting"},
        {"id": 4, "name": "Example Producer", "known_for_department": "Production"},
        {"id": 5, "name": "Unknown Profession"},
    ]

    def get(path, **params):
        if path == "search/person":
            return dict(
                results=people if params.get("page", 1) == 1 else [],
                total_results=100,
                total_pages=5,
            )
        if path == "person/525":
            return dict(people[0], movie_credits={"cast": [], "crew": []})
        return original(path, **params)

    app.extensions["tmdb"].get = get
    html = client.get("/search?q=nolan").data
    assert all(p["name"].encode() in html for p in people[:3])
    assert b"Example Producer" not in html and b"Unknown Profession" not in html
    assert b"DIRECTOR" in html and b"ACTOR" in html
    actors = client.get("/search?q=nolan&type=person").data
    assert b"Keanu Reeves" in actors and b"Christopher Nolan" in actors
    for url in ["/search?q=nolan&type=person"]:
        response = client.get(url)
        assert response.status_code == 200
        html = response.data
        assert b"Christopher Nolan" in html and b"Quentin Tarantino" in html
        assert b"Keanu Reeves" in html and b"Example Producer" not in html
        assert b"3 matches on this page" in html
        assert b"page=2" in html
    assert (
        b"No matches on this page."
        in client.get("/search?type=person&q=nolan&page=2").data
    )
    assert b"DIRECTOR" in client.get("/explore/person/525").data
    suggestions = client.get("/api/suggestions?q=nolan&type=person").json["results"]
    assert [m["label"] for m in suggestions] == [
        "Christopher Nolan",
        "Quentin Tarantino",
        "Keanu Reeves",
    ]
    assert [m["subtitle"] for m in suggestions] == ["Director", "Director", "Actor"]
    assert suggestions[0]["url"] == "/explore/person/525"
    all_suggestions = client.get("/api/suggestions?q=nolan").json["results"]
    assert any(
        m["label"] == "Christopher Nolan" and m["subtitle"] == "Director"
        for m in all_suggestions
    )


def test_writers_and_producers_link_from_movie_details(app, client):
    from tmdb_client import movie_details

    mock_tmdb(app)
    original = app.extensions["tmdb"].get
    crew = [
        {"id": 525, "name": "Christopher Nolan", "job": job}
        for job in ["Director", "Screenplay", "Story", "Producer", "Producer"]
    ] + [
        {"id": 600, "name": "A Writer", "job": "Novel"},
        {"id": 601, "name": "A Producer", "job": "Executive Producer"},
    ]
    movie = dict(MOVIE, credits=dict(MOVIE["credits"], crew=crew))

    def get(path, **params):
        if path == "movie/603":
            return movie
        return original(path, **params)

    app.extensions["tmdb"].get = get
    entities = movie_details(movie)["entities"]
    assert len(entities["directors"]) == 1
    assert len(entities["writers"]) == 2 and len(entities["producers"]) == 2
    assert entities["writers"][0]["role"] == "Screenplay, Story"
    assert entities["producers"][0]["role"] == "Producer"
    html = client.get("/catalog_movie/603").data
    assert b"Writing" in html and b"Producers" in html
    assert b"/explore/person/600" in html and b"/explore/person/601" in html
    assert client.get("/explore/person/600").status_code == 200
    assert client.get("/explore/person/601").status_code == 200


def test_search_checkbox_filters_and_pagination(app, client):
    mock_tmdb(app)
    original = app.extensions["tmdb"].get
    calls = []

    def get(path, **params):
        calls.append(path)
        if path == "search/person":
            return dict(
                results=[
                    dict(id=1, name="Actor Example", known_for_department="Acting"),
                    dict(
                        id=2, name="Director Example", known_for_department="Directing"
                    ),
                    dict(id=3, name="Writer Example", known_for_department="Writing"),
                ],
                total_pages=3,
                total_results=50,
            )
        return original(path, **params)

    app.extensions["tmdb"].get = get
    url = "/search?q=example&filters=1&category=director&category=company"
    html = client.get(url).data
    assert b"Director Example" in html and b"Warner Bros." in html
    assert b"Actor Example" not in html and b"Writer Example" not in html
    assert "search/movie" not in calls and calls.count("search/person") == 1
    from html import unescape

    next_link = next(
        unescape(link)
        for link in re.findall(r'href="([^"]+)"', html.decode())
        if "page=2" in link
    )
    assert "category=director" in next_link and "category=company" in next_link
    next_html = client.get(next_link).data
    assert b"Director Example" in next_html and b"Actor Example" not in next_html
    data = client.get("/api/suggestions?q=example&filters=1&category=actor").json[
        "results"
    ]
    assert [item["label"] for item in data] == ["Actor Example"]
    calls.clear()
    assert (
        b"Select at least one category"
        in client.get("/search?q=example&filters=1").data
    )
    assert client.get("/api/suggestions?q=example&filters=1").json["results"] == []
    assert not calls
