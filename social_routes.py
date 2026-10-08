"""Member directory and a read-only feed of consented showcase films."""

from flask import Blueprint, render_template, request, url_for

from cloud_client import CloudError
from public_catalog import present_public_movies
from social import decode_cursor, encode_cursor, normalize_query


def register_social(app, cloud):
    bp = Blueprint("social", __name__)

    @bp.get("/social")
    def page():
        view = request.args.get("view", "people")
        query, rows, result, next_url, state = "", [], None, None, None
        if view not in ("people", "week"):
            view, state = "people", "invalid"
        try:
            query = normalize_query(request.args.get("q", ""))
            cursor = decode_cursor(request.args.get("cursor", ""), view, query)
        except (ValueError, TypeError, KeyError):
            state = "invalid"
        if state is None:
            try:
                if not cloud.public_ready or not hasattr(cloud.client, "social_page"):
                    state = "setup"
                else:
                    result = cloud.client.social_page(view, query, cursor)
                    rows = result["rows"]
                    if view == "week" and rows:
                        library = cloud.current()
                        movies = present_public_movies(
                            library, rows, app.extensions["i18n"]["language"]()
                        )
                        rows = [dict(row, movie=movies[row["tmdb_id"]]) for row in rows]
                    if result["next_cursor"]:
                        next_url = url_for(
                            "social.page",
                            view=view,
                            q=query,
                            cursor=encode_cursor(view, query, result["next_cursor"]),
                        )
            except CloudError as error:
                state = "setup" if error.kind == "setup" else "offline"
            except (ValueError, TypeError, KeyError):
                state = "offline"
        status = 400 if state == "invalid" else 503 if state else 200
        return render_template(
            "social.html",
            view=view,
            query=query,
            rows=rows if state is None else [],
            result=result,
            next_url=next_url,
            state=state,
        ), status

    app.register_blueprint(bp)
