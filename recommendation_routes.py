"""Recommendation and onboarding UI, sharing the existing TMDB and library services."""

import json
from concurrent.futures import ThreadPoolExecutor

from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from recommendations import MODES, Recommender, build_profile
from storage import utcnow


def register_recommendations(app, db, tmdb, download_poster, service=None):
    bp = Blueprint("recommendations", __name__)
    t = app.extensions["i18n"]["translate"]
    language = app.extensions["i18n"]["language"]
    catalog = app.extensions["catalog"]
    service = service if service is not None else Recommender(db, tmdb, catalog)
    app.extensions["recommender"] = service

    def setting(key, default=""):
        rows = db.query("SELECT value FROM settings WHERE key=?", key)
        return rows[0]["value"] if rows else default

    def mode_value():
        mode = setting("recommendation_mode", "balanced")
        return mode if mode in MODES else "balanced"

    @bp.get("/recommendations")
    def index():
        profile = build_profile(service.library())
        return render_template(
            "recommendations.html",
            profile=profile,
            mode=mode_value(),
            modes=MODES,
            onboarding=setting("recommendation_onboarding"),
            dismissed=db.query(
                "SELECT * FROM recommendation_dismissals ORDER BY created_at DESC"
            ),
        )

    @bp.post("/api/recommendations/refresh")
    @bp.get("/api/recommendations")
    def results():
        data = dict(service.recommend(mode_value(), refresh=request.method == "POST"))
        data["movies"] = catalog.present(
            data["movies"], language(), fetch=language() == "tr"
        )
        data["waiting"] = catalog.present(data["waiting"], language())
        return jsonify(
            profile_changed=data.get("profile_changed", False),
            html=render_template(
                "_recommendations.html", current_url="/recommendations", **data
            ),
        )

    @bp.get("/taste")
    def taste():
        selected = db.query("""SELECT m.tmdb_id,m.title,m.poster_path FROM recommendation_likes l
            JOIN movies m ON m.id=l.movie_id WHERE m.deleted_at IS NULL AND m.tmdb_id IS NOT NULL ORDER BY l.created_at""")
        return render_template(
            "taste.html",
            selected=catalog.present(selected, language()),
            mode=mode_value(),
            modes=MODES,
        )

    @bp.get("/api/taste/choices")
    def choices():
        query = request.args.get("q", "").strip()[:200]
        try:
            page = max(1, min(500 if query else 20, int(request.args.get("page", "1"))))
        except ValueError:
            abort(400, "Choose a valid page.")
        movies, pages, errors = service.survey_choices(
            query, page, language="tr-TR" if language() == "tr" else "en-US"
        )
        movies = catalog.present(movies, language())
        return jsonify(
            movies=movies, pages=pages, errors=[t(error) for error in errors]
        )

    @bp.post("/taste/save")
    def save():
        raw_ids = request.form.getlist("movie_id")
        try:
            ids = list(dict.fromkeys(int(mid) for mid in raw_ids))
        except ValueError:
            abort(400, "Choose valid movies.")
        if not ids or len(ids) > 24 or any(mid < 1 for mid in ids):
            abort(400, "Select between 1 and 24 movies. Three to five is a good start.")
        mode = request.form.get("mode", "balanced")
        if mode not in MODES:
            abort(400, "Choose a valid discovery preference.")
        existing = {
            row["tmdb_id"]
            for row in db.query("SELECT tmdb_id FROM movies WHERE tmdb_id IS NOT NULL")
        }

        bound_details = catalog.details

        def prepare(mid):
            if mid in existing:
                return mid, {}
            details = bound_details(mid)
            values = {
                k: details.get(k)
                for k in (
                    "title",
                    "year",
                    "genre",
                    "overview",
                    "runtime",
                    "director",
                    "score_percent",
                )
            }
            values.update(
                poster_path=download_poster(mid, details["poster_url"]),
                cast_list=", ".join(details["cast"]),
                entities_json=json.dumps(details["entities"]),
            )
            # Historical selections have no known watch date; never invent today's date.
            return mid, values

        with ThreadPoolExecutor(max_workers=4) as pool:
            entries = list(pool.map(prepare, ids))
        created = db.save_survey(entries, mode)
        service.invalidate()
        flash(
            t(
                "Your taste profile is saved. {count} new movies added as watched; existing entries kept.",
                count=created,
            )
        )
        return jsonify(url=url_for("recommendations.index"), created=created)

    @bp.post("/taste/skip")
    def skip():
        db.execute(
            "INSERT OR REPLACE INTO settings(key,value) VALUES ('recommendation_onboarding','skipped')"
        )
        return redirect(url_for("recommendations.index"))

    @bp.post("/recommendations/mode")
    def change_mode():
        mode = request.form.get("mode")
        if mode not in MODES:
            abort(400, "Choose a valid discovery preference.")
        db.execute(
            "INSERT OR REPLACE INTO settings(key,value) VALUES ('recommendation_mode',?)",
            mode,
        )
        return redirect(url_for("recommendations.index"))

    @bp.post("/recommendations/dismiss")
    def dismiss():
        try:
            mid = int(request.form.get("movie_id", ""))
            if mid < 1:
                raise ValueError
        except ValueError:
            abort(400, "Choose a valid movie.")
        title = request.form.get("title", "Movie")[:300]
        db.execute(
            "INSERT OR IGNORE INTO recommendation_dismissals(tmdb_id,title,created_at) VALUES (?,?,?)",
            mid,
            title,
            utcnow(),
        )
        return jsonify(ok=True)

    @bp.post("/recommendations/restore")
    def restore():
        try:
            mid = int(request.form.get("movie_id", ""))
        except ValueError:
            abort(400, "Choose a valid movie.")
        db.execute("DELETE FROM recommendation_dismissals WHERE tmdb_id=?", mid)
        return redirect(url_for("recommendations.index"))

    app.register_blueprint(bp)
