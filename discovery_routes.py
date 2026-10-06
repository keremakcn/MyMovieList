"""Discovery views share the existing add/edit actions and TMDB gateway client."""

from flask import Blueprint, abort, jsonify, render_template, request

from discovery import COLLECTIONS, GENRES, DiscoveryService
from tmdb_client import TMDBError


def register_discovery(app, db, tmdb):
    bp = Blueprint("discovery", __name__)
    service = DiscoveryService(tmdb, db)
    language = app.extensions["i18n"]["language"]
    catalog = app.extensions["catalog"]

    def localized_feed(collection, **options):
        locale = language()
        data = service.feed(collection, language="tr-TR" if locale == "tr" else "en-US", **options)
        data["movies"] = catalog.present(data["movies"], locale)
        return data
    app.extensions["discovery"] = service

    def options(api=False):
        def number(name, default, maximum):
            value = request.args.get(name, str(default))
            if (len(value) > len(str(maximum)) or not value.isascii()
                    or not value.isdecimal()):
                abort(400, f"Choose a valid {name}.")
            result = int(value)
            if not 1 <= result <= maximum:
                abort(400, f"Choose a {name} between 1 and {maximum}.")
            return result

        page = number("page", 1, 500)
        window = request.args.get("window", "week")
        if window not in ("day", "week"):
            abort(400, "Choose daily or weekly trends.")
        raw_genre = request.args.get("genre")
        genre = None
        if raw_genre is not None:
            if (len(raw_genre) > 5 or not raw_genre.isascii()
                    or not raw_genre.isdecimal()):
                abort(400, "Choose a valid movie genre.")
            genre = int(raw_genre)
            if genre not in GENRES:
                abort(400, "Choose a valid movie genre.")
        hide = request.args.get("hide_library", "0")
        if hide not in ("0", "1"):
            abort(400, "Choose whether to hide library films.")
        return {"page": page, "window": window, "genre": genre,
                    "hide_library": hide == "1", "limit": number("limit", 12, 20) if api else 20}

    @bp.get("/discover/<collection>")
    def collection_page(collection):
        if collection not in COLLECTIONS:
            abort(404, "This movie collection does not exist.")
        selected = options()
        try:
            data = localized_feed(collection, **selected)
        except TMDBError as error:
            info = COLLECTIONS[collection]
            data = dict(
                collection=collection, collection_info=info, title=info["title"],
                description=info["description"], genres=GENRES, movies=[],
                pages=0, total=0, total_provider=0, visible_count=0,
                hidden_count=0, error=str(error), **selected,
            )
        return render_template("discovery.html", **data)

    @bp.get("/api/discovery/<collection>")
    def collection_feed(collection):
        if collection not in COLLECTIONS or collection == "genres":
            abort(404, "This movie collection does not exist.")
        data = localized_feed(collection, **options(api=True))
        return jsonify(
            html=render_template("_discovery_feed.html", current_url="/search", **data),
            page=data["page"], pages=data["pages"], total=data["total_provider"],
            visible_count=data["visible_count"], hidden_count=data["hidden_count"],
        )

    app.register_blueprint(bp)
