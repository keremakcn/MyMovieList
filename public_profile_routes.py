"""Anonymous visits to the consented public projection, with local add actions."""

from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

from flask import Blueprint, abort, render_template, request

from account_username import normalize_username
from cloud_client import CloudError
from tmdb_client import TMDBError


def register_public_profiles(app, cloud):
    bp = Blueprint("public_profiles", __name__)

    @bp.get("/profiles/<uuid:share_id>")
    @bp.get("/profiles/u/<username>")
    def visit(share_id=None, username=None):
        if not cloud.public_ready:
            abort(503)
        try:
            if username is not None:
                try:
                    username = normalize_username(username)
                except ValueError:
                    abort(404)
                public = cloud.client.public_profile_by_username(username)
            else:
                public = cloud.client.public_profile(str(share_id))
        except (CloudError, ValueError, TypeError):
            return render_template(
                "public_profile.html", public=None, unavailable=True
            ), 503
        if (
            not public["found"]
            or (share_id is not None and UUID(public["share_id"]) != share_id)
            or (username is not None and public.get("username") != username)
        ):
            return render_template(
                "public_profile.html", public=None, unavailable=False
            ), 404
        library = cloud.current()
        locale = app.extensions["i18n"]["language"]()

        def movie(pick):
            # Catalog fetches never import another user's personal record.
            try:
                details = library.catalog.details(pick["tmdb_id"])
            except (TMDBError, ValueError, TypeError):
                details = {
                    "tmdb_id": pick["tmdb_id"],
                    "title": "#" + str(pick["tmdb_id"]),
                    "overview": "",
                    "year": None,
                    "poster_url": None,
                    "score_percent": None,
                }
            rows = library.db.query(
                "SELECT * FROM movies WHERE tmdb_id=? AND deleted_at IS NULL",
                pick["tmdb_id"],
            )
            return dict(
                details,
                library=dict(rows[0]) if rows else None,
                showcase_rating=pick.get("rating"),
            )

        with ThreadPoolExecutor(max_workers=3) as executor:
            movies = list(executor.map(movie, public["films"]))
        movies = library.catalog.present(movies, locale)
        return render_template(
            "public_profile.html",
            public=public,
            movies=movies,
            current_url=request.path,
            unavailable=False,
        )

    app.register_blueprint(bp)
