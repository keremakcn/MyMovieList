"""MyMovieList: local library and TMDB discovery, shared by web and desktop."""

import json
import os
import secrets
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from itertools import zip_longest
from pathlib import Path
from threading import Lock
from urllib.parse import urlencode, urlsplit
from urllib.request import urlopen

from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)

from catalog import display_summary
from i18n import SUPPORTED_LANGUAGES, register_i18n
from storage import Database
from tmdb_client import TMDBClient, TMDBError, image_url, movie_summary
from version import APP_VERSION

BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
DEFAULT_DATA_DIR = (
    Path(os.environ.get("APPDATA", str(Path.home()))) / "MovieWatchlist"
    if getattr(sys, "frozen", False)
    else BASE_DIR
)
SORTS = {
    "": "Library order",
    "added_desc": "Recently added",
    "added_asc": "First added",
    "rating_desc": "Your rating: high to low",
    "rating_asc": "Your rating: low to high",
    "tmdb_desc": "TMDB score: high to low",
    "tmdb_asc": "TMDB score: low to high",
    "year_desc": "Release year: newest",
    "year_asc": "Release year: oldest",
    "watched_desc": "Recently watched",
    "watched_asc": "Watched: oldest",
}
SORT_SQL = {
    "": "CASE WHEN favorite=1 THEN 1 WHEN status='Watched' THEN 2 ELSE 3 END, order_key DESC",
    "added_desc": "order_key DESC",
    "added_asc": "order_key ASC",
}
for field, column in [
    ("rating", "rating"),
    ("tmdb", "score_percent"),
    ("year", "year"),
    ("watched", "watched_date"),
]:
    for direction in ("asc", "desc"):
        SORT_SQL[f"{field}_{direction}"] = (
            f"({column} IS NULL), {column} {direction}, order_key DESC"
        )


def safe_path(value, default="/"):
    if (
        not value
        or not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or any(ord(c) < 32 for c in value)
    ):
        return default
    parts = urlsplit(value)
    return value if not parts.scheme and not parts.netloc else default


def create_app(config=None):
    app = Flask(
        __name__,
        template_folder=str(BASE_DIR / "templates"),
        static_folder=str(BASE_DIR / "static"),
    )
    data_dir = Path(
        (config or {}).get("DATA_DIR")
        or os.environ.get("MOVIE_WATCHLIST_DATA_DIR", DEFAULT_DATA_DIR)
    )
    load_dotenv(data_dir / ".env")
    app.config.update(
        SECRET_KEY=os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32),
        DATA_DIR=str(data_dir),
        DATABASE=str(data_dir / "movies.db"),
        MAX_CONTENT_LENGTH=1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        TRUSTED_HOSTS=["localhost", "127.0.0.1", "[::1]"],
    )
    if config:
        app.config.update(config)
    device_db = Database(app.config["DATABASE"])
    device_db.migrate()
    register_i18n(app, device_db)
    t = app.extensions["i18n"]["translate"]
    locks = [Lock() for _ in range(32)]

    tmdb = TMDBClient()
    app.extensions["tmdb"] = tmdb
    from cloud_sync import CloudWorkspace

    cloud = CloudWorkspace(app, device_db, tmdb)
    app.extensions["cloud"] = cloud
    db, catalog = cloud.db, cloud.catalog
    app.extensions["db"] = db
    app.extensions["catalog"] = catalog

    @app.before_request
    def bind_library():
        cloud.bind()
        if request.path == "/account/import":
            request.max_content_length = 50 * 1024 * 1024

    def content_locale():
        return app.extensions["i18n"]["language"]()

    def provider_language():
        return "tr-TR" if content_locale() == "tr" else "en-US"

    app.jinja_env.filters["safe_back"] = safe_path

    def csrf_token():
        if "csrf_token" not in session or session.get("csrf_scope") != cloud.scope():
            session["csrf_token"] = secrets.token_urlsafe(32)
            session["csrf_scope"] = cloud.scope()
        return session["csrf_token"]

    def wants_json():
        return (
            request.path.startswith("/api/")
            or request.headers.get("Accept") == "application/json"
        )

    @app.context_processor
    def shared_context():
        def page_url(page):
            args = request.args.to_dict(flat=False)
            args.update(request.view_args or {})
            args["page"] = page
            return url_for(request.endpoint, **args)

        # Keep one return destination; do not recursively embed an entire browsing history.
        navigation_args = [
            (key, value)
            for key, value in request.args.items(multi=True)
            if key not in ("back", "next")
        ]
        current_url = request.path + (
            "?" + urlencode(navigation_args) if navigation_args else ""
        )
        return {
            "app_version": APP_VERSION,
            "library_scope": cloud.scope(),
            "account_status": cloud.status(),
            "csrf_token": csrf_token,
            "current_url": current_url,
            "page_url": page_url,
            "entity_page_url": page_url,
            "back_url": safe_path(request.args.get("back"), "/search"),
            "asset_version": str(
                max(
                    (BASE_DIR / "static/style.css").stat().st_mtime_ns,
                    (BASE_DIR / "static/script.js").stat().st_mtime_ns,
                    (BASE_DIR / "static/recommendations.js").stat().st_mtime_ns,
                    (BASE_DIR / "static/discovery.js").stat().st_mtime_ns
                    if (BASE_DIR / "static/discovery.js").exists()
                    else 0,
                    (BASE_DIR / "static/i18n.js").stat().st_mtime_ns,
                    (BASE_DIR / "static/account.js").stat().st_mtime_ns,
                    (BASE_DIR / "static/showcase.js").stat().st_mtime_ns,
                    (BASE_DIR / "static/locales/tr.json").stat().st_mtime_ns,
                )
            ),
        }

    @app.before_request
    def protect_writes():
        scope = request.headers.get("X-Library-Scope")
        if scope and scope != cloud.scope():
            abort(409, "Your account changed. Reload the page before continuing.")
        if request.method == "POST":
            supplied = request.headers.get("X-CSRF-Token") or request.form.get(
                "csrf_token", ""
            )
            if (
                session.get("csrf_scope") != cloud.scope()
                or not supplied
                or not secrets.compare_digest(supplied, session.get("csrf_token", ""))
            ):
                abort(400, "This page has expired. Refresh it and try again.")
            origin = request.headers.get("Origin")
            if origin and origin != request.host_url.rstrip("/"):
                abort(403, "This request came from another site.")

    @app.after_request
    def security_headers(response):
        if request.method == "POST" and response.status_code < 400:
            cloud.wake.set()
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' https://image.tmdb.org data:; style-src 'self'; script-src 'self'; connect-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
        )
        if request.endpoint != "static" and request.endpoint != "poster_file":
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(TMDBError)
    def tmdb_error(error):
        if wants_json():
            return jsonify(error=t(str(error))), error.status
        return render_template("error.html", message=str(error)), error.status

    from werkzeug.exceptions import HTTPException, SecurityError

    @app.errorhandler(HTTPException)
    def http_error(error):
        if isinstance(error, SecurityError):
            return "Untrusted host.", 400
        if wants_json():
            return jsonify(error=t(error.description)), error.code
        return render_template("error.html", message=error.description), error.code

    @app.errorhandler(500)
    def internal_error(error):
        message = "Something went wrong. Your library is safe. Please try again."
        if wants_json():
            return jsonify(error=t(message)), 500
        return render_template("error.html", message=message), 500

    def integer(value, default=1, maximum=500):
        try:
            return max(1, min(int(value), maximum))
        except (ValueError, TypeError):
            return default

    def annotate(movies):
        membership = db.membership([m["tmdb_id"] for m in movies])
        for movie in movies:
            movie["library"] = membership.get(movie["tmdb_id"])
        return movies

    def unique_movies(items, locale=None):
        seen, result = set(), []
        for item in items:
            if item.get("id") and item["id"] not in seen:
                seen.add(item["id"])
                result.append(movie_summary(item))
        return catalog.present(result, locale or content_locale())

    @app.get("/")
    def index():
        status = request.args.get("status", "all")
        status = (
            status
            if status in ("all", "Watchlist", "Watched", "favorite", "trash")
            else "all"
        )
        sort = request.args.get("sort", "")
        sort = sort if sort in SORT_SQL else ""
        query = request.args.get("q", "").strip()[:200]
        clauses = [
            "deleted_at IS NOT NULL" if status == "trash" else "deleted_at IS NULL"
        ]
        params = []
        if status in ("Watchlist", "Watched"):
            clauses.append("status=?")
            params.append(status)
        elif status == "favorite":
            clauses.append("favorite=1")
        if query:
            clauses.append("""(search_fold(title) LIKE search_fold(?) ESCAPE '\\' OR EXISTS (
                SELECT 1 FROM movie_metadata c WHERE c.tmdb_id=movies.tmdb_id AND (
                search_fold(c.english_title) LIKE search_fold(?) ESCAPE '\\' OR
                search_fold(c.original_title) LIKE search_fold(?) ESCAPE '\\' OR
                search_fold(c.turkish_title) LIKE search_fold(?) ESCAPE '\\')))""")
            pattern = (
                "%"
                + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                + "%"
            )
            params.extend([pattern] * 4)
        where = " AND ".join(clauses)
        count = db.query("SELECT COUNT(*) total FROM movies WHERE " + where, *params)[
            0
        ]["total"]
        pages = max(1, (count + 35) // 36)
        page = integer(request.args.get("page"), maximum=pages)
        movies = db.query(
            "SELECT * FROM movies WHERE "
            + where
            + " ORDER BY "
            + SORT_SQL[sort]
            + " LIMIT 36 OFFSET ?",
            *params,
            (page - 1) * 36,
        )
        pending = catalog.schedule(movies)
        stats = db.library_stats()
        return render_template(
            "index.html",
            movies=[
                dict(m, metadata_pending=m.get("tmdb_id") in pending)
                for m in catalog.present(movies, content_locale())
            ],
            stats=stats,
            status_filter=status,
            sort=sort,
            sorts=SORTS,
            query=query,
            count=count,
            page=page,
            pages=pages,
        )

    @app.get("/api/library/metadata")
    def library_metadata():
        raw_ids = request.args.getlist("id")
        if (
            not raw_ids
            or len(raw_ids) > 36
            or any(
                not value.isascii() or not value.isdecimal() or len(value) > 10
                for value in raw_ids
            )
        ):
            abort(400, "Choose a valid movie.")
        ids = list(dict.fromkeys(int(value) for value in raw_ids))
        rows = db.query(
            "SELECT * FROM movies WHERE deleted_at IS NULL AND id IN ("
            + ",".join("?" for _ in ids)
            + ")",
            *ids,
        )
        with catalog.state_lock:
            pending = set(catalog.pending)
        return jsonify(
            language=content_locale(),
            movies=[
                {
                    "id": m["id"],
                    "title": m["title"],
                    "search_title": m["search_title"],
                    "pending": m.get("tmdb_id") in pending,
                }
                for m in catalog.present(rows, content_locale())
            ],
        )

    def profession(department):
        return {
            "Acting": "Actor",
            "Directing": "Director",
            "Production": "Producer",
            "Writing": "Writer",
            "Sound": "Sound",
            "Camera": "Cinematographer",
            "Editing": "Editor",
        }.get(department, department or "Film professional")

    def selected_categories():
        allowed = ("movie", "actor", "director", "company")
        if "filters" in request.args:
            return [key for key in allowed if key in request.args.getlist("category")]
        return {
            "movie": ["movie"],
            "person": ["actor", "director"],
            "company": ["company"],
        }.get(request.args.get("type"), ["movie", "actor", "director"])

    def search_data(query, kind, page, categories=None, locale=None):
        locale = locale or content_locale()
        if kind == "all":
            # All shares the same role filter and cache as Actors & Directors.
            categories = (
                categories if categories is not None else ["movie", "actor", "director"]
            )
            sources = []
            if "movie" in categories:
                sources.append(("movie", "Movies"))
            if "actor" in categories or "director" in categories:
                sources.append(("person", "Actors & Directors"))
            if "company" in categories:
                sources.append(("company", "Companies"))
            if not sources:
                return {
                    "results": [],
                    "page": page,
                    "pages": 0,
                    "total": 0,
                    "warnings": [],
                }
            groups, warnings, failures = [], [], []
            with ThreadPoolExecutor(max_workers=len(sources)) as pool:
                searches = [
                    (
                        label,
                        pool.submit(
                            search_data, query, source, page, categories, locale
                        ),
                    )
                    for source, label in sources
                ]
                for label, future in searches:
                    try:
                        groups.append(future.result())
                    except TMDBError as exc:
                        failures.append(exc)
                        warnings.append(f"{t(label)}: {t(str(exc))}")
            if not groups:
                raise failures[0]
            results = [
                item
                for row in zip_longest(*(group["results"] for group in groups))
                for item in row
                if item is not None
            ]
            return {
                "results": results,
                "page": page,
                "pages": max(group["pages"] for group in groups),
                "total": len(results),
                "warnings": warnings,
            }
        if kind not in ("movie", "person", "company"):
            abort(400, "Choose All, Movies, Actors & Directors or Companies.")
        departments = ()
        if kind == "person":
            categories = categories if categories is not None else ["actor", "director"]
            departments = tuple(
                role
                for key, role in (("actor", "Acting"), ("director", "Directing"))
                if key in categories
            )
        source = kind
        params = {"query": query, "page": page}
        if kind != "company":
            params.update(
                language="tr-TR" if locale == "tr" else "en-US", include_adult="false"
            )
        data = tmdb.get("search/" + source, **params)
        if kind == "movie":
            results = annotate(unique_movies(data.get("results", []), locale))
        else:
            results, seen = [], set()
            for item in data.get("results", []):
                if departments and item.get("known_for_department") not in departments:
                    continue
                if item["id"] in seen:
                    continue
                seen.add(item["id"])
                results.append(
                    {
                        "id": item["id"],
                        "name": item["name"],
                        "role_label": profession(item.get("known_for_department"))
                        if source == "person"
                        else "Company",
                        "image": image_url(
                            item.get("profile_path") or item.get("logo_path"), "w185"
                        ),
                        "description": ", ".join(
                            display_summary(dict(m, title=m.get("title", "")), locale)[
                                "title"
                            ]
                            for m in item.get("known_for", [])
                            if m.get("media_type") == "movie"
                        ),
                    }
                )
        for result in results:
            result["kind"] = source
        return {
            "results": results,
            "page": page,
            "pages": min(data.get("total_pages", 1), 500),
            "total": len(results) if departments else data.get("total_results", 0),
            "warnings": [],
        }

    @app.get("/search")
    def search():
        query = request.args.get("q", "").strip()[:200]
        kind = request.args.get("type", "all")
        if kind not in ("all", "movie", "person", "company"):
            kind = "all"
        data, error = (
            {"results": [], "page": 1, "pages": 0, "total": 0, "warnings": []},
            None,
        )
        selected = selected_categories()
        if "filters" in request.args:
            kind = "all"
        if query and not selected:
            error = "Select at least one category to search."
        elif query:
            try:
                data = search_data(
                    query, kind, integer(request.args.get("page")), selected
                )
            except TMDBError as exc:
                error = str(exc)
        return render_template(
            "search.html",
            query=query,
            kind=kind,
            selected_categories=selected,
            error=error,
            **data,
        )

    @app.get("/api/suggestions")
    def suggestions():
        query = request.args.get("q", "").strip()[:200]
        if len(query) < 2:
            return jsonify(results=[])
        kind = request.args.get("type", "all")
        if "filters" in request.args:
            kind = "all"
        data = search_data(query, kind, 1, selected_categories())
        return jsonify(
            results=[
                {
                    "label": m.get("title") or m.get("name"),
                    "subtitle": t(m.get("role_label", "Movie"))
                    + (
                        " · " + str(m.get("year") or m.get("description"))
                        if m.get("year") or m.get("description")
                        else ""
                    ),
                    "url": url_for("catalog_movie", tmdb_id=m["tmdb_id"])
                    if m["kind"] == "movie"
                    else url_for("entity", kind=m["kind"], entity_id=m["id"]),
                }
                for m in data["results"][:6]
            ]
        )

    def download_poster(tmdb_id, remote):
        if not remote:
            return None
        folder = Path(app.config["DATA_DIR"]) / "posters"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{tmdb_id}.jpg"
        if target.exists():
            return f"/posters/{target.name}"
        temp = None
        try:
            with urlopen(remote, timeout=5) as response:
                image = response.read(5 * 1024 * 1024 + 1)
                if len(image) > 5 * 1024 * 1024 or not response.headers.get(
                    "Content-Type", ""
                ).startswith("image/"):
                    return remote
            with tempfile.NamedTemporaryFile(dir=folder, delete=False) as output:
                temp = Path(output.name)
                output.write(image)
            os.replace(temp, target)
            return f"/posters/{target.name}"
        except OSError:
            return remote
        finally:
            if temp and temp.exists():
                temp.unlink()

    @app.get("/posters/<path:filename>")
    def poster_file(filename):
        return send_from_directory(
            Path(app.config["DATA_DIR"]) / "posters", filename, max_age=86400
        )

    def catalog_details(tmdb_id):
        return catalog.details(tmdb_id)

    def add_from_tmdb(status):
        try:
            tmdb_id = int(request.form.get("movie_id", ""))
            if tmdb_id < 1:
                raise ValueError
        except ValueError:
            abort(400, "Choose a valid movie.")
        with locks[tmdb_id % len(locks)]:
            existing = db.query("SELECT * FROM movies WHERE tmdb_id=?", tmdb_id)
            if existing:
                db.restore(existing[0]["id"])
                movie_id, created = existing[0]["id"], False
            else:
                details = catalog_details(tmdb_id)
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
                    tmdb_id=tmdb_id,
                    status=status,
                    watched_date=date.today().isoformat()
                    if status == "Watched"
                    else None,
                    poster_path=download_poster(tmdb_id, details["poster_url"]),
                    cast_list=", ".join(details["cast"]),
                    entities_json=json.dumps(details["entities"]),
                )
                movie_id, created = db.add_tmdb(values)
        if wants_json():
            return jsonify(
                id=movie_id,
                created=created,
                status=db.movie(movie_id)["status"],
                edit_url=url_for(
                    "edit", movie_id=movie_id, next=safe_path(request.form.get("next"))
                ),
            )
        flash(
            "Movie added to your library."
            if created
            else "Movie is already in your library."
        )
        return redirect(safe_path(request.form.get("next"), f"/movie/{movie_id}"))

    @app.post("/add_from_catalog")
    def add_from_catalog():
        return add_from_tmdb("Watchlist")

    @app.post("/add_watched_from_catalog")
    def add_watched_from_catalog():
        return add_from_tmdb("Watched")

    @app.get("/catalog_movie/<int:tmdb_id>")
    def catalog_movie(tmdb_id):
        details = catalog.present([catalog_details(tmdb_id)], content_locale())[0]
        details["library"] = db.membership([tmdb_id]).get(tmdb_id)
        return render_template("catalog_movie.html", movie=details, tmdb=details)

    @app.get("/movie/<int:movie_id>")
    def movie(movie_id):
        row = db.movie(movie_id)
        if not row:
            abort(404, "This movie is not in your active library.")
        row, details = catalog.library_detail(row, content_locale())
        return render_template("movie.html", movie=row, tmdb=details)

    @app.post("/movie/<int:movie_id>/refresh")
    def refresh_movie(movie_id):
        row = db.movie(movie_id)
        if not row or not row["tmdb_id"]:
            abort(404)
        details = catalog.details(row["tmdb_id"], force=True)
        db.execute(
            "UPDATE movies SET entities_json=?, overview=?, runtime=?, director=?, cast_list=?, score_percent=?, poster_path=? WHERE id=? AND deleted_at IS NULL",
            json.dumps(details["entities"]),
            details["overview"],
            details["runtime"],
            details["director"],
            ", ".join(details["cast"]),
            details["score_percent"],
            download_poster(row["tmdb_id"], details["poster_url"]),
            movie_id,
        )
        flash("Movie information updated. Your notes and rating are unchanged.")
        return redirect(url_for("movie", movie_id=movie_id))

    @app.get("/explore/<kind>/<int:entity_id>")
    def entity(kind, entity_id):
        if kind not in ("person", "company"):
            abort(404)
        page = integer(request.args.get("page"))
        profile = tmdb.get(
            f"{kind}/{entity_id}",
            **(
                {"language": provider_language(), "append_to_response": "movie_credits"}
                if kind == "person"
                else {}
            ),
        )
        if kind == "person":
            credits = profile.get("movie_credits", {})
            items = credits.get("cast", []) + credits.get("crew", [])
            items.sort(key=lambda m: m.get("popularity", 0), reverse=True)
            all_movies = unique_movies(items)
            total = len(all_movies)
            pages = max(1, (total + 23) // 24)
            page = min(page, pages)
            movies = all_movies[(page - 1) * 24 : page * 24]
        else:
            data = tmdb.get(
                "discover/movie",
                with_companies=entity_id,
                language=provider_language(),
                include_adult="false",
                sort_by="popularity.desc",
                page=page,
            )
            movies = unique_movies(data.get("results", []))
            pages, total = (
                min(data.get("total_pages", 1), 500),
                data.get("total_results", 0),
            )
        return render_template(
            "entity.html",
            profile=profile,
            role_label=profession(profile.get("known_for_department"))
            if kind == "person"
            else "Company",
            kind=kind,
            entity_id=entity_id,
            movies=annotate(movies),
            page=page,
            pages=pages,
            total=total,
            profile_image=image_url(
                profile.get("profile_path") or profile.get("logo_path")
            ),
        )

    def validate_form(form, manual=False):
        values = {
            "note": form.get("note", "").strip() or None,
            "watched_date": form.get("watched_date", "").strip() or None,
            "rating": None,
        }
        if len(values["note"] or "") > 20000:
            raise ValueError("Keep notes under 20,000 characters.")
        if form.get("rating", "").strip():
            try:
                values["rating"] = int(form["rating"])
            except ValueError:
                raise ValueError("Rating must be a whole number from 1 to 10.")
            if not 1 <= values["rating"] <= 10:
                raise ValueError("Rating must be between 1 and 10.")
        if values["watched_date"]:
            try:
                datetime.strptime(values["watched_date"], "%Y-%m-%d")
            except ValueError:
                raise ValueError("Enter a valid watched date.")
        if manual:
            values.update(
                title=form.get("title", "").strip(),
                genre=form.get("genre", "").strip() or None,
                year=None,
                status=form.get("status", "Watchlist"),
            )
            if not values["title"] or len(values["title"]) > 300:
                raise ValueError("Enter a title of 1–300 characters.")
            if values["status"] not in ("Watchlist", "Watched"):
                raise ValueError("Choose a valid status.")
            if form.get("year", "").strip():
                try:
                    values["year"] = int(form["year"])
                except ValueError:
                    raise ValueError("Enter a valid release year.")
                if not 1800 <= values["year"] <= 2200:
                    raise ValueError("Release year must be between 1800 and 2200.")
            if values["status"] == "Watched" and not values["watched_date"]:
                values["watched_date"] = date.today().isoformat()
        return values

    @app.route("/add", methods=["GET", "POST"])
    def add():
        error = None
        if request.method == "POST":
            try:
                values = validate_form(request.form, manual=True)
                movie_id = db.add_custom(values)
                return redirect(url_for("movie", movie_id=movie_id))
            except ValueError as exc:
                error = str(exc)
        return render_template(
            "add.html", error=error, values=request.form
        ), 422 if error else 200

    @app.route("/edit/<int:movie_id>", methods=["GET", "POST"])
    def edit(movie_id):
        row = db.movie(movie_id)
        if not row:
            abort(404)
        next_url = safe_path(request.args.get("next"), f"/movie/{movie_id}")
        error = None
        if request.method == "POST":
            try:
                values = validate_form(request.form)
                db.update_personal(movie_id, values)
                flash("Changes saved.")
                return redirect(next_url)
            except ValueError as exc:
                error = str(exc)
                row.update(
                    {
                        k: request.form.get(k, "")
                        for k in ("rating", "note", "watched_date")
                    }
                )
        return render_template(
            "edit.html",
            movie=catalog.present([row], content_locale())[0],
            next_url=next_url,
            error=error,
        ), 422 if error else 200

    def mutation_result(movie_id):
        row = db.movie(movie_id)
        if not row:
            abort(404)
        if wants_json():
            return jsonify(
                id=movie_id,
                status=row["status"],
                favorite=row["favorite"],
                watched_date=row["watched_date"],
            )
        return redirect(safe_path(request.form.get("next")))

    @app.post("/favorite/<int:movie_id>")
    def favorite(movie_id):
        value = request.form.get("value")
        if value not in ("0", "1"):
            abort(400, "Choose the desired favorite state.")
        db.update_personal(movie_id, {"favorite": int(value)})
        return mutation_result(movie_id)

    @app.post("/status/<int:movie_id>")
    def change_status(movie_id):
        value = request.form.get("value")
        if value not in ("Watchlist", "Watched"):
            abort(400, "Choose a valid watch status.")
        row = db.movie(movie_id)
        if not row:
            abort(404)
        db.update_personal(
            movie_id,
            {
                "status": value,
                "watched_date": (row["watched_date"] or date.today().isoformat())
                if value == "Watched"
                else None,
            },
        )
        return mutation_result(movie_id)

    @app.post("/delete/<int:movie_id>")
    def delete(movie_id):
        marker = db.remove(movie_id)
        if not marker:
            abort(404)
        if wants_json():
            return jsonify(id=movie_id, marker=marker)
        flash("Movie removed. You can restore it from Recently removed.")
        return redirect(safe_path(request.form.get("next")))

    @app.post("/restore/<int:movie_id>")
    def restore(movie_id):
        if not db.restore(movie_id, request.form.get("marker")):
            abort(
                409,
                "This movie changed since that notification. Restore it from Recently removed.",
            )
        if wants_json():
            return jsonify(id=movie_id)
        flash("Movie restored with its original notes, rating and position.")
        return redirect(safe_path(request.form.get("next")))

    @app.get("/settings")
    def settings():
        return render_template("settings.html")

    @app.get("/api/ui-language")
    def ui_language():
        return jsonify(language=app.extensions["i18n"]["language"]())

    @app.post("/settings/language")
    def change_language():
        choice = request.form.get("language")
        if choice not in SUPPORTED_LANGUAGES:
            abort(400, "Choose Turkish or English.")
        device_db.execute(
            "INSERT OR REPLACE INTO settings(key,value) VALUES ('ui_language',?)",
            choice,
        )
        # Capture the new locale for the confirmation and response headers.
        from flask import g

        g.ui_language = choice
        flash(t("Language saved."))
        return redirect(url_for("settings"), code=303)

    from recommendation_routes import register_recommendations

    register_recommendations(app, db, tmdb, download_poster, service=cloud.recommender)
    from discovery_routes import register_discovery

    register_discovery(app, db, tmdb)
    from account_routes import register_accounts

    register_accounts(app, cloud)
    from public_profile_routes import register_public_profiles
    register_public_profiles(app, cloud)
    return app


if __name__ == "__main__":
    import threading
    import webbrowser

    from waitress import serve

    application = create_app()
    threading.Timer(1, lambda: webbrowser.open("http://127.0.0.1:5000")).start()
    serve(application, host="127.0.0.1", port=5000)
