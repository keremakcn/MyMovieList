import copy
from datetime import date
from html.parser import HTMLParser
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pytest

from discovery import GENRES, DiscoveryService
from tmdb_client import TMDBClient, TMDBError


def movie(mid, **extra):
    data = {"id": mid, "title": f"Film {mid}", "adult": False, "video": False,
            "release_date": "2026-10-01", "vote_average": 8.1, "vote_count": 123,
            "overview": "A story worth discovering.", "poster_path": None}
    data.update(extra)
    return data


def service_for(app, rows=None, pages=4):
    payload = {"results": rows if rows is not None else [movie(100), movie(101)],
                   "total_pages": pages, "total_results": 80}
    tmdb = Mock()
    tmdb.get.return_value = payload
    service = DiscoveryService(tmdb, app.extensions["db"],
                               today=lambda: date(2026, 10, 6))
    return service, tmdb, payload


@pytest.mark.parametrize("collection,window,path", [
    ("trending", "week", "trending/movie/week"),
    ("trending", "day", "trending/movie/day"),
    ("top-rated", "week", "movie/top_rated"),
])
def test_public_collections_use_distinct_ordered_provider_lists(app, collection, window, path):
    service, tmdb, _ = service_for(app, rows=[movie(101), movie(100)])
    data = service.feed(collection, window=window, page=2)
    tmdb.get.assert_called_once_with(path, language="en-US", page=2)
    assert [entry["tmdb_id"] for entry in data["movies"]] == [101, 100]
    assert data["total_provider"] == 80 and data["visible_count"] == 2


def test_new_releases_use_recent_past_dates_and_adult_video_exclusions(app):
    service, tmdb, _ = service_for(app)
    service.feed("new-releases")
    tmdb.get.assert_called_once_with(
        "discover/movie", language="en-US", page=1, include_adult="false",
        include_video="false", sort_by="popularity.desc",
        **{"primary_release_date.gte": "2026-07-08", "primary_release_date.lte": "2026-10-06"},
    )


def test_genre_picker_needs_no_online_metadata_or_movies(app):
    service, tmdb, _ = service_for(app)
    data = service.feed("genres")
    tmdb.get.assert_not_called()
    assert data["genres"] == GENRES and len(GENRES) == 19
    assert data["movies"] == [] and data["genre"] is None
    service.feed("genres", genre=878)
    params = tmdb.get.call_args.kwargs
    assert params["with_genres"] == 878
    assert params["primary_release_date.lte"] == "2026-10-06"


def test_invalid_and_duplicate_provider_rows_are_filtered_without_cache_mutation(app):
    rows = [
        movie(100), movie(100), dict(movie(101), adult=True), dict(movie(102), video=True),
        {"id": True}, {"id": "100"}, {"id": 0}, {"id": -4}, {"id": 10_000_000_000},
        None, "unexpected", dict(movie(103), title=None, overview=123,
                                 poster_path=3, vote_average=10 ** 1000),
    ]
    service, _, payload = service_for(app, rows)
    before = copy.deepcopy(payload)
    membership = Mock(wraps=service.db.membership)
    service.db.membership = membership
    result = service.feed("trending")
    assert [entry["tmdb_id"] for entry in result["movies"]] == [100, 103]
    assert result["movies"][1]["title"] == "Untitled movie"
    assert result["movies"][1]["score_percent"] is None
    assert payload == before
    assert all("library" not in row for row in rows if isinstance(row, dict))
    membership.assert_called_once_with([100, 103])


def test_membership_and_hide_are_live_while_provider_data_is_cached(app):
    service, tmdb, payload = service_for(app)
    before = copy.deepcopy(payload)
    assert all(entry["library"] is None for entry in service.feed("trending")["movies"])
    local_id, _ = service.db.add_tmdb({"tmdb_id": 100, "title": "Film 100", "status": "Watchlist"})
    result = service.feed("trending")
    assert result["movies"][0]["library"]["id"] == local_id
    filtered = service.feed("trending", hide_library=True)
    assert [entry["tmdb_id"] for entry in filtered["movies"]] == [101]
    assert filtered["hidden_count"] == 1 and filtered["total_provider"] == 80
    service.db.remove(local_id)
    restored_to_feed = service.feed("trending", hide_library=True)
    assert [entry["tmdb_id"] for entry in restored_to_feed["movies"]] == [100, 101]
    assert payload == before
    assert tmdb.get.call_count == 4


def test_hide_entire_page_does_not_erase_pagination_or_claim_filtered_total(app):
    service, _, _ = service_for(app)
    for mid in (100, 101):
        service.db.add_tmdb({"tmdb_id": mid, "title": f"Film {mid}", "status": "Watchlist"})
    result = service.feed("top-rated", hide_library=True)
    assert result["movies"] == [] and result["visible_count"] == 0
    assert result["hidden_count"] == 2 and result["pages"] == 4
    assert result["total_provider"] == 80


def test_discovery_limits_results_after_filtering_and_caps_provider_pagination(app):
    service, _, _ = service_for(app, rows=[movie(mid) for mid in range(100, 130)], pages=1000)
    result = service.feed("trending", limit=12)
    assert len(result["movies"]) == 12 and result["pages"] == 500
    assert [entry["tmdb_id"] for entry in result["movies"]] == list(range(100, 112))


@pytest.mark.parametrize("kwargs", [
    {"collection": "unknown"}, {"collection": "trending", "page": 0},
    {"collection": "trending", "page": 501}, {"collection": "trending", "window": "year"},
    {"collection": "genres", "genre": 12345}, {"collection": "genres", "genre": True},
    {"collection": "trending", "limit": 21},
])
def test_service_validation_happens_before_network(app, kwargs):
    service, tmdb, _ = service_for(app)
    with pytest.raises(ValueError):
        service.feed(**kwargs)
    tmdb.get.assert_not_called()


@pytest.mark.parametrize("query", [
    "page=0", "page=501", "page=abc", "page=-1", "page=1.5",
    "window=month", "genre=12345", "genre=not-a-genre", "hide_library=yes",
    "limit=0", "limit=21", pytest.param("page=" + "9" * 5000, id="oversized-number"),
])
def test_invalid_api_filters_return_400_without_upstream_call(app, client, query):
    tmdb = app.extensions["tmdb"]
    tmdb.get = Mock()
    response = client.get("/api/discovery/trending?" + query)
    assert response.status_code == 400 and "error" in response.json
    tmdb.get.assert_not_called()


@pytest.mark.parametrize("url", ["/discover/unknown", "/api/discovery/unknown", "/api/discovery/genres"])
def test_unknown_collections_return_404_before_network(app, client, url):
    app.extensions["tmdb"].get = Mock()
    assert client.get(url).status_code == 404
    app.extensions["tmdb"].get.assert_not_called()


def stub_route_provider(app):
    calls = []

    def request(path, params):
        calls.append((path, params))
        if path == "movie/100":
            return dict(movie(100), genres=[], credits={"cast": [], "crew": []})
        return {"results": [movie(100), movie(101)], "total_pages": 4, "total_results": 80}

    app.extensions["tmdb"]._request = request
    return calls


def test_api_quick_add_and_duplicate_are_reflected_across_cached_collections(app, client):
    from test_app import post

    calls = stub_route_provider(app)
    first = client.get("/api/discovery/trending").json
    assert first["page"] == 1 and first["total"] == 80
    assert 'action="/add_from_catalog"' in first["html"]
    added = post(client, "/add_from_catalog", movie_id=100, next="/search").json
    duplicate = post(client, "/add_from_catalog", movie_id=100, next="/search").json
    assert added["created"] and not duplicate["created"] and duplicate["id"] == added["id"]
    second = client.get("/api/discovery/trending").json
    assert 'aria-label="Edit Film 100 — ' in second["html"]
    assert 'In your library"' in second["html"]
    assert [path for path, _ in calls].count("trending/movie/week") == 1
    hidden = client.get("/api/discovery/trending?hide_library=1").json
    assert hidden["visible_count"] == 1 and hidden["hidden_count"] == 1
    assert "Film 100" not in hidden["html"] and "Film 101" in hidden["html"]
    assert client.get("/api/discovery/top-rated").json["visible_count"] == 2
    assert len(app.extensions["db"].query("SELECT * FROM movies")) == 1
    app.extensions["db"].execute("UPDATE movies SET status='Watched' WHERE tmdb_id=?", 100)
    watched = client.get("/api/discovery/trending").json["html"]
    assert 'aria-label="Edit Film 100 — Watched"' in watched


def test_api_provider_error_is_independent_from_other_collections_and_library(app, client):
    def request(path, **params):
        if path.startswith("trending/"):
            raise TMDBError("Movie discovery is temporarily unavailable.", 503)
        return {"results": [movie(100)], "total_pages": 1, "total_results": 1}

    app.extensions["tmdb"].get = request
    error = client.get("/api/discovery/trending")
    assert error.status_code == 503 and "unavailable" in error.json["error"]
    assert client.get("/api/discovery/top-rated").status_code == 200
    assert client.get("/").status_code == 200


def test_genre_page_without_selection_is_available_offline(app, client):
    app.extensions["tmdb"].get = Mock(side_effect=TMDBError("Offline."))
    page = client.get("/discover/genres")
    assert page.status_code == 200 and b"Science Fiction" in page.data
    app.extensions["tmdb"].get.assert_not_called()


def test_ssr_navigation_preserves_collection_filters_and_pagination(app, client):
    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.hrefs = []

        def handle_starttag(self, tag, attrs):
            if tag == "a":
                self.hrefs.append(dict(attrs).get("href", ""))

    stub_route_provider(app)
    response = client.get("/discover/trending?window=day&hide_library=1&page=2")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "window=day" in html and "hide_library=1" in html
    assert "page=3" in html and "page=1" in html
    links = Links()
    links.feed(html)
    details = [href for href in links.hrefs if href.startswith("/catalog_movie/")]
    assert details
    assert parse_qs(urlsplit(details[0]).query)["back"] == [
        "/discover/trending?window=day&hide_library=1&page=2"
    ]


def test_ssr_provider_error_keeps_filter_controls_and_saved_library_available(app, client):
    app.extensions["tmdb"].get = Mock(side_effect=TMDBError("Try again shortly.", 503))
    response = client.get("/discover/new-releases?hide_library=1")
    assert response.status_code == 200 and b"Try again shortly." in response.data
    assert b"hide_library" in response.data and client.get("/").status_code == 200


def test_movie_genres_match_existing_taste_profile():
    from recommendations import GENRES as profile_genres

    assert GENRES == profile_genres


def test_discovery_cache_expires_sooner_than_movie_details(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("tmdb_client.time.monotonic", lambda: clock[0])
    client = TMDBClient()
    client._request = Mock(return_value={"results": []})
    paths = ["trending/movie/week", "movie/top_rated", "discover/movie", "movie/100"]
    for path in paths:
        client.get(path)
    assert client._request.call_count == 4
    clock[0] += 1801
    for path in paths:
        client.get(path)
    assert client._request.call_count == 7
    clock[0] += 21600
    client.get("movie/100")
    assert client._request.call_count == 8
