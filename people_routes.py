"""Private person preferences remain usable without a cloud account."""

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

from tmdb_client import TMDBError, image_url


def register_people(app, cloud):
    bp = Blueprint("people", __name__)
    locale = app.extensions["i18n"]["language"]

    @bp.post("/people/<role>/<int:person_id>/favorite")
    def favorite(role, person_id):
        if role not in ("actor", "director") or not 1 <= person_id <= 9999999999:
            abort(404)
        if request.form.get("favorite") not in ("0", "1"):
            abort(422)
        library = cloud.current()
        # Display-only hints from a previously shown cast card never enter sync.
        if request.form.get("name"):
            library.people.cache(
                person_id,
                {
                    "name": request.form["name"],
                    "profile_path": request.form.get("profile_path"),
                    "portrait_url": request.form.get("portrait_url"),
                },
                locale(),
            )
        try:
            library.people.set(person_id, role, request.form["favorite"] == "1")
        except ValueError as error:
            abort(422, str(error))
        if request.accept_mimetypes.best == "application/json":
            return jsonify(
                person_id=person_id, role=role, favorite=request.form["favorite"] == "1"
            )
        from app import safe_path

        flash(
            "Added to favorite people."
            if request.form["favorite"] == "1"
            else "Removed from favorite people."
        )
        return redirect(safe_path(request.form.get("next"), url_for("people.index")))

    @bp.get("/people/favorites")
    def index():
        role = request.args.get("role", "actor")
        if role not in ("actor", "director"):
            abort(404)
        try:
            page = max(1, min(417, int(request.args.get("page", 1))))
        except ValueError:
            page = 1
        store = cloud.current().people
        count, people = store.listing(role, locale(), page)
        pages = max(1, (count + 23) // 24)
        if page > pages:
            page = pages
            _, people = store.listing(role, locale(), page)
        # Fetch missing names only for this page, bounded and outside library sync.
        # One connectivity failure stops the batch; cached cards remain usable.
        for person in people:
            if store.metadata(person["id"], locale()):
                continue
            try:
                details = cloud.tmdb.get(
                    f"person/{person['id']}",
                    language="tr-TR" if locale() == "tr" else "en-US",
                )
                if details.get("id") != person["id"]:
                    continue
                store.cache(person["id"], details, locale())
                person.update(details)
            except TMDBError:
                break
        for person in people:
            person["portrait_url"] = image_url(person.get("profile_path"), "w185")
            person["role"] = app.extensions["i18n"]["translate"](
                "Actor" if role == "actor" else "Director"
            )
        return render_template(
            "people_favorites.html",
            people=people,
            favorite_role=role,
            total=count,
            page=page,
            pages=pages,
        )

    app.register_blueprint(bp)
