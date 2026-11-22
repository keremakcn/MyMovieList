"""Tests for pure cinema statistics, the /stats route, backdrop validation and packaging."""

import json
import re
from pathlib import Path

import pytest
from test_app import MOVIE, mock_tmdb, post

import scripts.verify_macos as verify_macos
from cinema_stats import compute_cinema_stats, decade_label_tr
from tmdb_client import movie_details, movie_summary, safe_backdrop_url


def test_empty_library_stats_and_encouraging_empty_state(app, client):
    db = app.extensions["db"]
    stats = compute_cinema_stats(db, year=2026)
    assert stats["year"] == 2026
    assert stats["totals"] == {
        "total": 0,
        "watched": 0,
        "watchlist": 0,
        "favorites": 0,
        "rated": 0,
        "with_notes": 0,
        "watched_this_year": 0,
        "avg_rating": None,
        "total_minutes": 0,
        "total_hours": 0,
        "runtime_count": 0,
    }
    assert len(stats["rating_distribution"]) == 10
    assert all(
        b["count"] == 0 and b["bar_height"] == 0 for b in stats["rating_distribution"]
    )
    assert len(stats["monthly_activity"]) == 12
    assert all(
        m["count"] == 0 and m["bar_height"] == 0 for m in stats["monthly_activity"]
    )
    assert stats["top_genres"] == []
    assert stats["decades"] == []
    assert stats["top_directors"] == []
    assert stats["top_actors"] == []

    response = client.get("/stats")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "data-stats-empty" in html
    assert "Your cinema stats start with your first film" in html
    assert 'href="/search"' in html
    assert 'href="/settings#external-import"' in html
    assert "style=" not in html


def test_compute_cinema_stats_aggregates_and_excludes_deleted(app):
    db = app.extensions["db"]
    # 1. Watched TMDB film with entities_json, runtime, rating, note, 2026 date
    id1, _ = db.add_tmdb(
        {
            "tmdb_id": 603,
            "title": "The Matrix",
            "year": 1999,
            "genre": "Action, Science Fiction",
            "status": "Watched",
            "rating": 9,
            "favorite": 1,
            "note": "Private screening note that must never leak into stats.",
            "watched_date": "2026-03-15",
            "runtime": 136,
            "director": "Lana Wachowski, Lilly Wachowski",
            "cast_list": "Keanu Reeves, Carrie-Anne Moss",
            "entities_json": json.dumps(
                {
                    "directors": [
                        {"id": 9340, "name": "Lana Wachowski"},
                        {"id": 9339, "name": "Lilly Wachowski"},
                    ],
                    "cast": [
                        {"id": 6384, "name": "Keanu Reeves"},
                        {"id": 530, "name": "Carrie-Anne Moss"},
                    ],
                }
            ),
        }
    )
    # 2. Second watched film sharing director & actor via text fallback (merges into TMDB id)
    id2 = db.add_custom(
        {
            "title": "John Wick",
            "year": 2014,
            "genre": "Action, Thriller",
            "status": "Watched",
            "rating": 8,
            "favorite": 0,
            "note": None,
            "watched_date": "2026-03-28",
            "runtime": 101,
            "director": "Lana Wachowski",
            "cast_list": "Keanu Reeves, Willem Dafoe",
        }
    )
    # 3. Watchlist film (counts in total, watchlist, genres, decades, rating if rated;
    #    excluded from watched runtime and watched directors/actors)
    id3 = db.add_custom(
        {
            "title": "Stalker",
            "year": 1979,
            "genre": "Science Fiction, Drama",
            "status": "Watchlist",
            "rating": None,
            "favorite": 1,
            "note": "Watch on a rainy Sunday",
            "watched_date": None,
            "runtime": 162,
            "director": "Andrei Tarkovsky",
            "cast_list": "Alexander Kaidanovsky",
        }
    )
    # 4. Deleted film must be completely ignored
    deleted_id, _ = db.add_tmdb(
        {
            "tmdb_id": 999,
            "title": "Deleted Film",
            "year": 1985,
            "genre": "Horror",
            "status": "Watched",
            "rating": 2,
            "favorite": 1,
            "note": "Deleted note",
            "watched_date": "2026-01-10",
            "runtime": 200,
            "director": "Deleted Director",
            "cast_list": "Deleted Actor",
        }
    )
    assert id1 and id2 and id3 and deleted_id
    db.remove(deleted_id)

    stats = compute_cinema_stats(db, year=2026)
    totals = stats["totals"]
    assert totals["total"] == 3
    assert totals["watched"] == 2
    assert totals["watchlist"] == 1
    assert totals["favorites"] == 2
    assert totals["rated"] == 2
    assert totals["with_notes"] == 2
    assert totals["watched_this_year"] == 2
    assert totals["avg_rating"] == 8.5
    assert totals["total_minutes"] == 237
    assert totals["total_hours"] == 3
    assert totals["runtime_count"] == 2

    # Rating histogram (1..10)
    by_rating = {item["rating"]: item for item in stats["rating_distribution"]}
    assert by_rating[8]["count"] == 1 and by_rating[8]["bar_height"] == 100
    assert by_rating[9]["count"] == 1 and by_rating[9]["bar_height"] == 100
    assert by_rating[2]["count"] == 0 and by_rating[2]["bar_height"] == 0

    # Genres
    genres = {g["name"]: g for g in stats["top_genres"]}
    assert set(genres) == {"Action", "Science Fiction", "Thriller", "Drama"}
    assert genres["Action"]["count"] == 2
    assert genres["Action"]["avg_rating"] == 8.5
    assert genres["Action"]["bar_width"] == 100
    assert genres["Science Fiction"]["count"] == 2
    assert genres["Science Fiction"]["avg_rating"] == 9.0
    assert genres["Drama"]["count"] == 1
    assert genres["Drama"]["avg_rating"] is None
    assert genres["Drama"]["bar_width"] == 50

    # Decades in chronological order
    assert [d["decade"] for d in stats["decades"]] == ["1970s", "1990s", "2010s"]
    assert [d["start_year"] for d in stats["decades"]] == [1970, 1990, 2010]
    assert all(d["bar_width"] == 100 for d in stats["decades"])

    # Monthly activity for 2026
    months = {m["month"]: m for m in stats["monthly_activity"]}
    assert months[3]["count"] == 2 and months[3]["bar_height"] == 100
    assert all(
        months[m]["count"] == 0 and months[m]["bar_height"] == 0
        for m in range(1, 13)
        if m != 3
    )

    # Top watched directors & actors preserve TMDB IDs when merged with text credits
    top_dir = stats["top_directors"][0]
    assert top_dir == {
        "id": 9340,
        "name": "Lana Wachowski",
        "count": 2,
        "avg_rating": 8.5,
    }
    assert all(d["name"] != "Andrei Tarkovsky" for d in stats["top_directors"])
    assert all(d["name"] != "Deleted Director" for d in stats["top_directors"])

    top_actor = stats["top_actors"][0]
    assert top_actor == {
        "id": 6384,
        "name": "Keanu Reeves",
        "count": 2,
        "avg_rating": 8.5,
    }
    assert "Private screening note" not in json.dumps(stats)


def test_stats_route_renders_bilingual_editorial_charts_without_inline_styles(
    app, client
):
    db = app.extensions["db"]
    db.add_tmdb(
        {
            "tmdb_id": 603,
            "title": "The Matrix",
            "year": 1999,
            "genre": "Science Fiction, Action",
            "status": "Watched",
            "rating": 10,
            "favorite": 1,
            "note": "Private note",
            "watched_date": "2026-05-12",
            "runtime": 136,
            "director": "Lana Wachowski",
            "cast_list": "Keanu Reeves",
            "entities_json": json.dumps(
                {
                    "directors": [{"id": 9340, "name": "Lana Wachowski"}],
                    "cast": [{"id": 6384, "name": "Keanu Reeves"}],
                }
            ),
        }
    )

    # English
    en_res = client.get("/stats")
    assert en_res.status_code == 200
    en_html = en_res.get_data(as_text=True)
    nav = en_html.split('<nav class="app-nav"', 1)[1].split("</nav>", 1)[0]
    assert nav.count('aria-current="page"') == 1
    assert re.search(r'href="/stats"\s+aria-current="page"', nav)
    assert "Cinema stats" in en_html
    assert "Rating distribution" in en_html
    assert "Most watched directors" in en_html
    assert "Most watched actors" in en_html
    assert "1990s" in en_html
    assert "2h 16m" in en_html
    assert "/explore/person/9340" in en_html
    assert "/explore/person/6384" in en_html
    assert "<svg" in en_html and "<rect" in en_html
    assert "style=" not in en_html
    assert "Private note" not in en_html

    # Turkish
    post(client, "/settings/language", language="tr")
    tr_res = client.get("/stats")
    assert tr_res.status_code == 200
    assert tr_res.headers["Content-Language"] == "tr"
    tr_html = tr_res.get_data(as_text=True)
    assert "Sinema istatistikleri" in tr_html
    assert "Puan dağılımı" in tr_html
    assert "Öne çıkan türler" in tr_html
    assert "Bilim kurgu" in tr_html
    assert "En çok izlenen yönetmenler" in tr_html
    assert "En çok izlenen oyuncular" in tr_html
    assert "1990&#39;lar" in tr_html or "1990'lar" in tr_html
    assert "2 sa 16 dk" in tr_html
    assert "style=" not in tr_html
    assert decade_label_tr(1990) == "1990'lar"
    assert decade_label_tr(2000) == "2000'ler"
    assert decade_label_tr(2020) == "2020'ler"


@pytest.mark.parametrize(
    "raw_value,expected",
    [
        ("/f89U3ADr1oiB1s9GkdPOEpXUk5H.jpg", "https://image.tmdb.org/t/p/w1280/f89U3ADr1oiB1s9GkdPOEpXUk5H.jpg"),
        ("/valid_name-123.webp", "https://image.tmdb.org/t/p/w1280/valid_name-123.webp"),
        ("https://image.tmdb.org/t/p/w1280/abc_123.png", "https://image.tmdb.org/t/p/w1280/abc_123.png"),
        (None, None),
        ("", None),
        ("abc.jpg", None),
        ("/../../etc/passwd.jpg", None),
        ("/evil.svg", None),
        ("https://evil.example/p/w1280/abc.jpg", None),
        ("javascript:alert(1)", None),
    ],
)
def test_backdrop_url_validation(raw_value, expected):
    assert safe_backdrop_url(raw_value) == expected
    summary = movie_summary({"id": 603, "title": "The Matrix", "backdrop_path": raw_value})
    assert summary["backdrop_url"] == expected
    details = movie_details({"id": 603, "title": "The Matrix", "backdrop_path": raw_value})
    assert details["backdrop_url"] == expected


def test_movie_and_catalog_movie_render_backdrop_only_when_valid(app, client):
    with_backdrop = dict(MOVIE, backdrop_path="/f89U3ADr1oiB1s9GkdPOEpXUk5H.jpg")
    app.extensions["tmdb"].get = lambda path, **params: with_backdrop

    catalog_html = client.get("/catalog_movie/603").get_data(as_text=True)
    assert 'class="detail-backdrop"' in catalog_html
    assert (
        'src="https://image.tmdb.org/t/p/w1280/f89U3ADr1oiB1s9GkdPOEpXUk5H.jpg"'
        in catalog_html
    )

    added = post(client, "/add_from_catalog", movie_id="603")
    movie_id = added.json["id"]
    movie_html = client.get(f"/movie/{movie_id}").get_data(as_text=True)
    assert 'class="detail-backdrop"' in movie_html
    assert (
        'src="https://image.tmdb.org/t/p/w1280/f89U3ADr1oiB1s9GkdPOEpXUk5H.jpg"'
        in movie_html
    )

    # Custom / no-backdrop film renders cleanly without a broken image container
    mock_tmdb(app)
    custom_id = app.extensions["db"].add_custom(
        {"title": "Custom No Backdrop", "year": 2022, "status": "Watched"}
    )
    custom_html = client.get(f"/movie/{custom_id}").get_data(as_text=True)
    assert 'class="detail-backdrop"' not in custom_html


def test_packaging_allowlists_include_cinema_stats():
    root = Path(__file__).resolve().parents[1]
    gradle = (root / "android" / "app" / "build.gradle").read_text(encoding="utf-8")
    assert "'cinema_stats.py'" in gradle
    assert "cinema_stats" in verify_macos.MODULES
