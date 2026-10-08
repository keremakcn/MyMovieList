"""Anonymous visits to the consented public projection, with local add actions."""

from uuid import UUID

from flask import Blueprint, abort, render_template, request

from account_username import normalize_username
from cloud_client import CloudError
from public_catalog import present_public_movies


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

        resolved = present_public_movies(library, public["films"], locale)
        movies = [
            dict(resolved[pick["tmdb_id"]], showcase_rating=pick.get("rating"))
            for pick in public["films"]
        ]
        return render_template(
            "public_profile.html",
            public=public,
            movies=movies,
            current_url=request.path,
            unavailable=False,
        )

    app.register_blueprint(bp)
