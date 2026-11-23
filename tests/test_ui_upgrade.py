"""Tests for the v3.8 Desktop & Android UI upgrade (quick rating, poster grid toggle, KPI links, backdrop hero)."""

import json
import re

from app import create_app


def _client_with_movie(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "DATA_DIR": str(tmp_path),
            "DATABASE": str(tmp_path / "movies.db"),
        }
    )
    db = app.extensions["db"]
    movie_id, _ = db.add_tmdb(
        {
            "tmdb_id": 603,
            "title": "The Matrix",
            "year": 1999,
            "genre": "Action, Science Fiction",
            "status": "Watched",
            "rating": 8,
            "favorite": 1,
            "note": "Still iconic.",
        }
    )
    client = app.test_client()
    client.get("/")
    with client.session_transaction() as sess:
        csrf = sess["csrf_token"]
    return app, client, movie_id, csrf


def test_library_renders_clickable_kpis_and_view_switcher(tmp_path):
    app, client, movie_id, _ = _client_with_movie(tmp_path)
    try:
        html = client.get("/").get_data(as_text=True)
        assert 'data-library-view="cards"' in html
        assert 'data-library-view="posters"' in html
        assert 'href="/stats"' in html
        assert 'class="poster-rating-pill"' in html
        assert 'class="poster-note-pill"' in html
        assert 'class="poster-favorite-pill" data-poster-favorite' in html
        assert f'href="/movie/{movie_id}' in html
    finally:
        app.extensions["cloud"].close()


def test_expanded_cinema_stats_page_and_year_selector(tmp_path):
    app, client, _, _ = _client_with_movie(tmp_path)
    try:
        db = app.extensions["db"]
        db.execute(
            "UPDATE movies SET runtime=136, watched_date='2025-11-14', score_percent=82, "
            "entities_json=? WHERE tmdb_id=603",
            '{"directors":[{"id":9339,"name":"Lana Wachowski"}],"cast":[{"id":6384,"name":"Keanu Reeves"}],"companies":[{"id":174,"name":"Warner Bros. Pictures"}]}',
        )
        db.add_tmdb(
            {
                "tmdb_id": 550,
                "title": "Fight Club",
                "year": 1999,
                "genre": "Drama",
                "status": "Watched",
                "rating": 10,
                "favorite": 1,
                "watched_date": "2025-11-15",
            }
        )
        db.execute("UPDATE movies SET runtime=139, score_percent=84 WHERE tmdb_id=550")
        html = client.get("/stats?year=2025").get_data(as_text=True)
        assert "stats-hero-banner" in html
        assert "stats-ring-svg" in html
        assert "data-stats-records" in html
        assert "data-stats-weekdays" in html
        assert "data-stats-runtimes" in html
        assert "data-stats-studios" in html
        assert "data-stats-top-films" in html
        assert "Warner Bros. Pictures" in html
        assert "2025" in html
        assert 'id="open-stats-card"' in html
        assert 'id="stats-card-dialog"' in html
        assert 'id="stats-card-canvas" class="stats-card-canvas" width="1080" height="1350"' in html
        assert 'id="stats-card-download"' in html
        assert 'id="stats-card-copy"' in html
        assert "/static/stats_card.js?v=" in html

        match = re.search(
            r'<script id="cinema-stats-data" type="application/json">(.*?)</script>',
            html,
            re.DOTALL,
        )
        assert match is not None
        raw_stats_json = match.group(1)
        assert "Still iconic." not in raw_stats_json
        parsed_stats = json.loads(raw_stats_json)
        assert parsed_stats["year"] == 2025
        assert parsed_stats["totals"]["watched"] == 2

        js_res = client.get("/static/stats_card.js")
        assert js_res.status_code == 200
        assert b"renderCinemaPassport" in js_res.data
    finally:
        app.extensions["cloud"].close()


def test_quick_rate_endpoint_supports_ajax_form_clear_validation_and_csrf(tmp_path):
    app, client, movie_id, csrf = _client_with_movie(tmp_path)
    try:
        # CSRF required
        assert client.post(f"/rate/{movie_id}", data={"value": "9"}).status_code == 400

        # JSON AJAX update
        res = client.post(
            f"/rate/{movie_id}",
            data={"value": "10"},
            headers={"Accept": "application/json", "X-CSRF-Token": csrf},
        )
        assert res.status_code == 200
        assert res.get_json()["rating"] == 10
        assert app.extensions["db"].movie(movie_id)["rating"] == 10

        # Clear rating
        cleared = client.post(
            f"/rate/{movie_id}",
            data={"value": ""},
            headers={"Accept": "application/json", "X-CSRF-Token": csrf},
        )
        assert cleared.status_code == 200
        assert cleared.get_json()["rating"] is None
        assert app.extensions["db"].movie(movie_id)["rating"] is None

        # Reject invalid values
        for bad in ("0", "11", "abc"):
            assert (
                client.post(
                    f"/rate/{movie_id}",
                    data={"value": bad},
                    headers={"Accept": "application/json", "X-CSRF-Token": csrf},
                ).status_code
                == 400
            )

        # Standard form POST redirects cleanly
        redirect_res = client.post(
            f"/rate/{movie_id}",
            data={"value": "9", "csrf_token": csrf, "next": f"/movie/{movie_id}"},
        )
        assert redirect_res.status_code == 302
        assert app.extensions["db"].movie(movie_id)["rating"] == 9
    finally:
        app.extensions["cloud"].close()


def test_movie_detail_and_edit_render_quick_rating_strip(tmp_path):
    app, client, movie_id, _ = _client_with_movie(tmp_path)
    try:
        detail_html = client.get(f"/movie/{movie_id}").get_data(as_text=True)
        assert "data-quick-rate-form" in detail_html
        assert 'value="8"' in detail_html
        assert "data-rating-readout" in detail_html

        edit_html = client.get(f"/edit/{movie_id}").get_data(as_text=True)
        assert "data-edit-rating-strip" in edit_html
        assert 'data-edit-rate="8"' in edit_html
    finally:
        app.extensions["cloud"].close()
