"""Optional email/password accounts and portable library controls."""

import json
import re
import sqlite3
from datetime import date, datetime, timezone
from io import BytesIO

from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

from account_profile import AVATARS, showcase_settings, validate_showcase
from account_username import normalize_username
from auth_flows import AuthFlows
from cloud_client import CloudError
from name_policy import require_allowed_name
from personal_data import from_movie
from profile_sharing import sharing_badge, sharing_label


def register_accounts(app, cloud):
    bp = Blueprint("accounts", __name__)
    t = app.extensions["i18n"]["translate"]
    flows = AuthFlows()
    app.extensions["auth_flows"] = flows

    @app.template_filter("profile_date")
    def profile_date(value):
        try:
            parsed = date.fromisoformat(value)
        except (TypeError, ValueError):
            return value or ""
        if app.extensions["i18n"]["language"]() == "tr":
            return parsed.strftime("%d.%m.%Y")
        return parsed.strftime("%d %b %Y")

    def ready():
        if not cloud.ready or not cloud.client:
            raise CloudError(
                "Cloud accounts are being prepared. You can keep using your local library.",
                "setup",
            )

    def email():
        value = request.form.get("email", "").strip()
        if len(value) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid email address.")
        return value

    def password(name="password"):
        value = request.form.get(name, "")
        if not 8 <= len(value) <= 512:
            raise ValueError("Use a password of 8–512 characters.")
        return value

    def page(error=None, flow=None):
        # Auth operations are online-only: a transport error must not imply that
        # a password change or registration has been saved in the local library.
        if isinstance(error, CloudError):
            if error.kind == "offline":
                error = "Could not reach the account service. Check your connection and try again."
            elif error.kind == "limited":
                error = (
                    "Account service is temporarily limited. Please wait and try again."
                )
        status = cloud.status()
        flow = (
            flow
            or request.args.get("flow")
            or ("profile" if status["signed_in"] else "signin")
        )
        if flow not in (
            "signin",
            "signup",
            "verify",
            "username",
            "recover",
            "reset-code",
            "password",
            "reset",
            "profile",
            "personalize",
            "edit-profile",
            "edit-showcase",
            "settings",
        ):
            flow = "signin"
        pending = flows.view(session.get("auth_flow"), cloud.scope())
        required = {
            "verify": ("signup", "code"),
            "username": ("signup", "username"),
            "password": ("signup", "password"),
            "reset-code": ("recovery", "code"),
            "reset": ("recovery", "password"),
        }
        if flow in required and (
            not pending or (pending["purpose"], pending["stage"]) != required[flow]
        ):
            flow = "signup" if flow in ("verify", "username", "password") else "recover"
            error = error or "This verification has expired. Request a new code."
        if (
            flow
            in ("profile", "personalize", "edit-profile", "edit-showcase", "settings")
            and not status["signed_in"]
        ):
            flow = "signin"
        if status["owner"] and flow == "signup":
            flow = "profile"
            error = error or "Sign out before creating a new account on this device."
        conflicts = []
        if status["owner"] and flow == "settings":
            for r in cloud.current().db.query("""SELECT c.*,m.title,m.id FROM sync_conflicts c
                JOIN movies m ON m.record_key=c.record_key ORDER BY m.order_key"""):
                conflicts.append(
                    dict(
                        r,
                        local=from_movie(
                            cloud.current().db.movie(r["id"], include_deleted=True)
                        ),
                        remote=json.loads(r["remote_json"]),
                    )
                )
        shelves = None
        view = "personal" if request.args.get("view") == "personal" else "showcase"
        selection = showcase_settings(status["profile"])
        library = cloud.current()
        locale = app.extensions["i18n"]["language"]()
        if flow == "profile":
            shelves = (
                library.db.profile_films()
                if view == "personal"
                else {"showcase": library.db.showcase_films(selection["record_keys"])}
            )
            for key in ("favorites", "recent") if view == "personal" else ("showcase",):
                shelves[key] = library.catalog.present(shelves[key], locale)
        choices, selected_movies = None, []
        if flow == "edit-showcase":
            if error:
                try:
                    selection = validate_showcase(showcase_input())
                except (ValueError, TypeError):
                    pass
            choices = library.db.showcase_choices("", 1)
            choices["movies"] = library.catalog.present(choices["movies"], locale)
            resolved = {
                m["record_key"]: m
                for m in library.catalog.present(
                    library.db.showcase_films(selection["record_keys"]), locale
                )
            }
            selected_movies = [
                dict(resolved.get(key, {}), record_key=key)
                for key in selection["record_keys"]
            ]
        draft = dict(status["profile"])
        if error and flow == "edit-profile":
            draft["display_name"] = request.form.get(
                "display_name", draft["display_name"]
            )
            avatar = request.form.get("avatar_id")
            if avatar in dict(AVATARS):
                draft["avatar_id"] = avatar
        return render_template(
            "account.html",
            cloud_status=status,
            sharing_label=sharing_label(status["sharing"]),
            sharing_badge=sharing_badge(status["sharing"]),
            error=str(error) if error else None,
            flow=flow,
            email=(
                pending["email"]
                if pending
                else request.form.get("email") or session.get("account_email", "")
            )[:254],
            avatars=AVATARS,
            profile_stats=cloud.current().db.library_stats()
            if flow == "profile" and (view == "personal" or selection["show_stats"])
            else None,
            profile_shelves=shelves,
            profile_view=view,
            showcase=selection,
            showcase_choices=choices,
            showcase_selected=selected_movies,
            profile_form=draft,
            username_draft=request.form.get("username", "")[:24] if error else "",
            registration_username=pending.get("username", "") if pending else "",
            resend_after=max(0, int(60 - (flows.clock() - pending["sent_at"])) + 1)
            if pending
            else 0,
            guest_count=cloud.guest.library_stats()["total"],
            conflicts=conflicts,
        )

    @bp.get("/account")
    def account():
        return page()

    @bp.get("/account/settings")
    def settings():
        return page(flow="settings")

    @bp.post("/account/sharing")
    def sharing():
        library = cloud.current()
        status = cloud.status()
        if not status["signed_in"] or not library.owner:
            abort(403)
        action = request.form.get("action")
        if action not in ("publish", "unpublish"):
            return page("Choose a valid sharing action.", flow="profile"), 422
        view = library.sharing.view()
        if not view["ready"]:
            return page(
                "Public profiles are being prepared. Your showcase stays private.",
                flow="profile",
            ), 503
        if action == "publish":
            if request.form.get("consent") != "1":
                return page(
                    "Confirm that anyone with the link can see your showcase.",
                    flow="profile",
                ), 422
            if not status["enabled"]:
                return page(
                    "Resume cloud sync before publishing your showcase.", flow="profile"
                ), 422
            if not view["checked"] or view["error"]:
                return page(
                    "Wait for sharing to be checked, then try again.", flow="profile"
                ), 503
        # Persist consent/revocation first. The single sync worker serializes
        # network operations and retries; an interrupted request loses no intent.
        library.sharing.queue(action, status["profile"])
        cloud.wake.set()
        return redirect(url_for("accounts.account") + "#profile-sharing", code=303)

    def showcase_input():
        raw = request.form.get("record_keys", "[]")
        if len(raw) > 1000:
            raise ValueError("Choose up to 6 films for your showcase.")
        flags = [
            request.form.get(field, "0") for field in ("show_ratings", "show_stats")
        ]
        if any(value not in ("0", "1") for value in flags):
            raise ValueError("Choose valid showcase settings.")
        try:
            keys = json.loads(raw)
        except ValueError:
            raise ValueError("Choose films from your current library.") from None
        return {
            "record_keys": keys,
            "show_ratings": flags[0] == "1",
            "show_stats": flags[1] == "1",
        }

    @bp.post("/account/showcase")
    def showcase():
        if not cloud.status()["signed_in"] or not cloud.current().owner:
            abort(403)
        try:
            cloud.current().profile.save({"showcase": showcase_input()})
            flash("Showcase saved. Only the films you chose appear here.")
            return redirect(url_for("accounts.account"), code=303)
        except (ValueError, TypeError) as error:
            return page(error, flow="edit-showcase"), 422

    @bp.get("/api/account/showcase/films")
    def showcase_choices():
        if not cloud.status()["signed_in"] or not cloud.current().owner:
            abort(403)
        query = request.args.get("q", "").strip()[:200]
        try:
            page_number = min(1_000_000, max(1, int(request.args.get("page", "1"))))
        except ValueError:
            page_number = 1
        library = cloud.current()
        data = library.db.showcase_choices(query, page_number)
        data["movies"] = library.catalog.present(
            data["movies"], app.extensions["i18n"]["language"]()
        )
        return jsonify(data)

    @bp.post("/account/signin")
    def signin():
        try:
            ready()
            address, secret = email(), password()
            cloud.client.health()
            cloud.accept_session(cloud.client.sign_in(address, secret))
            flows.discard(session.pop("auth_flow", None))
            session["account_email"] = address
            session.pop("csrf_token", None)
            session.pop("csrf_scope", None)
            flash("Signed in. Your account library is open on this device.")
            return redirect(url_for("accounts.account"), code=303)
        except (CloudError, ValueError, OSError) as error:
            return page(
                error
                if not isinstance(error, OSError)
                else "Could not protect the account session. Your library is unchanged.",
                flow="signin",
            ), 422

    def new_flow(purpose, address):
        if purpose == "signup" and (cloud.selected or cloud.current().owner):
            raise ValueError("Sign out before creating a new account on this device.")
        current = flows.view(session.get("auth_flow"), cloud.scope())
        if (
            current
            and current["purpose"] == purpose
            and current["email"].casefold() == address.casefold()
            and flows.clock() - current["sent_at"] < 60
        ):
            raise ValueError("Please wait before requesting another code.")
        if purpose == "signup":
            cloud.client.health()
            cloud.client.username_health()
            cloud.client.begin_signup(address)
        else:
            cloud.client.recover(address)
        flows.discard(session.pop("auth_flow", None))
        session["auth_flow"] = flows.start(purpose, address, cloud.scope())
        session["account_email"] = address

    @bp.post("/account/signup")
    def signup():
        try:
            ready()
            new_flow("signup", email())
            return redirect(url_for("accounts.account", flow="verify"), code=303)
        except (CloudError, ValueError) as error:
            return page(error, flow="signup"), 422

    @bp.post("/account/verify")
    def verify():
        try:
            ready()
            key = session.get("auth_flow")
            with flows.use(key, cloud.scope(), "signup", "code") as step:
                value = cloud.client.verify(
                    step["email"], request.form.get("code", "").strip()
                )
                if not value.get("registration_pending"):
                    # Verified existing emails go to password sign-in. Never
                    # overwrite a pre-existing password through registration.
                    flows.discard(key)
                    session.pop("auth_flow", None)
                    try:
                        cloud.client.sign_out(value["access_token"])
                    except CloudError:
                        pass
                    flash(
                        "This email already has an account. Sign in with your password."
                    )
                    return redirect(
                        url_for("accounts.account", flow="signin"), code=303
                    )
                flows.verified(step, value, stage="username")
            return redirect(url_for("accounts.account", flow="username"), code=303)
        except (CloudError, ValueError) as error:
            return page(error, flow="verify"), 422

    @bp.post("/account/register-username")
    def register_username():
        try:
            ready()
            with flows.use(
                session.get("auth_flow"), cloud.scope(), "signup", "username"
            ) as step:
                name = normalize_username(
                    request.form.get("username", ""), writing=True
                )
                reply = cloud.client.claim_username(
                    step["credentials"]["access_token"], name
                )
                if reply["status"] == "taken":
                    raise ValueError(
                        "This username is already taken. Choose another one."
                    )
                # An abandoned registration may already own a handle. Keep that
                # confirmed handle; neither retries nor a different form can rename it.
                step["username"] = reply["username"]
                step["stage"] = "password"
                if reply["status"] == "locked":
                    flash(
                        "Your username has already been chosen. Your display name can still change."
                    )
            return redirect(url_for("accounts.account", flow="password"), code=303)
        except (CloudError, ValueError) as error:
            return page(error, flow="username"), 422

    @bp.post("/account/create-password")
    def create_password():
        try:
            ready()
            new = password("new_password")
            if new != request.form.get("confirm_password", ""):
                raise ValueError("The passwords do not match.")
            key = session.get("auth_flow")
            with flows.use(key, cloud.scope(), "signup", "password") as step:
                name = step["username"]
                value = step["credentials"]
                try:
                    cloud.prepare_signup_library(value)
                except (sqlite3.Error, OSError):
                    raise ValueError(
                        "Could not copy your local library. Your saved films are unchanged. Please try again."
                    ) from None
                cloud.client.complete_signup(value["access_token"], new)
                with cloud.lock:
                    if cloud.scope() != cloud.epoch:
                        raise ValueError(
                            "Your account changed. Reload the page before continuing."
                        )
                    cloud.accept_session(value)
                    # The request is still bound to the guest library. Cache
                    # this confirmed handle in the newly accepted account only.
                    cloud.active().username.receive({"username": name})
                flows.discard(key)
            session.pop("auth_flow", None)
            session.pop("csrf_token", None)
            session.pop("csrf_scope", None)
            flash("Your account is ready. Your library syncs automatically.")
            if cloud.guest.library_stats()["total"]:
                flash(
                    "Your saved films are in your new account. Your original local library stays on this device."
                )
            return redirect(url_for("accounts.account", flow="personalize"), code=303)
        except (CloudError, ValueError, OSError) as error:
            return page(
                error
                if not isinstance(error, OSError)
                else "Could not protect the account session. Your library is unchanged.",
                flow="password",
            ), 422

    @bp.post("/account/recover")
    def recover():
        try:
            ready()
            new_flow("recovery", email())
            flash("If an account exists, a password reset code has been sent.")
            return redirect(url_for("accounts.account", flow="reset-code"), code=303)
        except (CloudError, ValueError) as error:
            return page(error, flow="recover"), 422

    @bp.post("/account/verify-reset")
    def verify_reset():
        try:
            ready()
            with flows.use(
                session.get("auth_flow"), cloud.scope(), "recovery", "code"
            ) as step:
                value = cloud.client.verify(
                    step["email"], request.form.get("code", "").strip(), "recovery"
                )
                flows.verified(step, value)
            return redirect(url_for("accounts.account", flow="reset"), code=303)
        except (CloudError, ValueError) as error:
            return page(error, flow="reset-code"), 422

    @bp.post("/account/reset")
    def reset():
        try:
            ready()
            new = password("new_password")
            if new != request.form.get("confirm_password", ""):
                raise ValueError("The passwords do not match.")
            key = session.get("auth_flow")
            with flows.use(key, cloud.scope(), "recovery", "password") as step:
                value = step["credentials"]
                cloud.client.change_password(value["access_token"], new)
                flows.discard(key)
            session.pop("auth_flow", None)
            try:
                cloud.client.sign_out(value["access_token"])
            except CloudError:
                pass
            if cloud.session and cloud.session["user_id"] == value["user_id"]:
                cloud.sign_out()
                session.pop("csrf_token", None)
                session.pop("csrf_scope", None)
            flash("Password updated. Sign in with your new password.")
            return redirect(url_for("accounts.account", flow="signin"), code=303)
        except (CloudError, ValueError) as error:
            return page(error, flow="reset"), 422

    @bp.post("/account/resend")
    def resend():
        pending = flows.view(session.get("auth_flow"), cloud.scope())
        destination = (
            "verify" if pending and pending["purpose"] == "signup" else "reset-code"
        )
        try:
            ready()
            if not pending:
                raise ValueError("This verification has expired. Request a new code.")
            with flows.use(
                session.get("auth_flow"), cloud.scope(), pending["purpose"], "code"
            ) as step:
                if flows.clock() - step["sent_at"] < 60:
                    raise ValueError("Please wait before requesting another code.")
                step["sent_at"] = flows.clock()
                if step["purpose"] == "signup":
                    cloud.client.begin_signup(step["email"])
                else:
                    cloud.client.recover(step["email"])
            flash("A new confirmation code has been sent.")
            return redirect(url_for("accounts.account", flow=destination), code=303)
        except (CloudError, ValueError) as error:
            return page(error, flow=destination), 422

    @bp.post("/account/profile")
    def profile():
        if not cloud.status()["signed_in"] or not cloud.current().owner:
            abort(403)
        try:
            require_allowed_name(request.form.get("display_name", ""))
            cloud.current().profile.save(
                {
                    "display_name": request.form.get("display_name", ""),
                    "avatar_id": request.form.get("avatar_id", ""),
                }
            )
            flash(
                "Profile saved. Changes sync automatically when connected."
                if cloud.enabled(cloud.current())
                else "Profile saved on this device. Sync is paused."
            )
            return redirect(url_for("accounts.account"), code=303)
        except ValueError as error:
            return page(error, flow="edit-profile"), 422

    @bp.post("/account/username")
    def choose_username():
        library = cloud.current()
        if not cloud.status()["signed_in"] or not library.owner:
            abort(403)
        try:
            if not library.username.ready:
                raise ValueError(
                    "Usernames are being prepared. You can still edit your name and avatar."
                )
            name = normalize_username(request.form.get("username", ""), writing=True)
            reply = cloud.authenticated_call(
                library.owner, cloud.client.claim_username, name
            )
            if reply["status"] == "taken":
                raise ValueError("This username is already taken. Choose another one.")
            library.username.receive({"username": reply["username"]})
            library.username.next_attempt = 0
            if reply["status"] == "locked":
                raise ValueError(
                    "Your username has already been chosen. Your display name can still change."
                )
            flash("Username saved. This is now your profile address.")
            return redirect(url_for("accounts.account", flow="edit-profile"), code=303)
        except CloudError as error:
            if error.kind == "validation":
                return page(str(error), flow="edit-profile"), 422
            message = (
                "Usernames are being prepared. You can still edit your name and avatar."
                if error.kind == "setup"
                else "Could not confirm your username. Check your connection and try again."
            )
            return page(message, flow="edit-profile"), 503
        except (ValueError, TypeError) as error:
            return page(str(error), flow="edit-profile"), 422

    @bp.post("/account/signout")
    def signout():
        flows.discard(session.get("auth_flow"))
        cloud.sign_out()
        session.clear()
        flash(
            "Signed out. Your original local library is open. Account records remain on this device."
        )
        return redirect(url_for("index"), code=303)

    @bp.post("/account/sync-settings")
    def sync_settings():
        if not cloud.current().owner:
            abort(400)
        value = request.form.get("enabled")
        if value not in ("0", "1"):
            abort(400)
        if value == "1":
            ready()
            if request.form.get("consent") != "yes":
                return page(
                    "Choose whether to upload your private library.", flow="settings"
                ), 422
        cloud.set_enabled(value == "1")
        flash(
            "Cloud sync enabled."
            if value == "1"
            else "Cloud sync paused. Your library stays on this device."
        )
        return redirect(url_for("accounts.settings"), code=303)

    @bp.post("/account/sync")
    def sync_now():
        ready()
        owner = cloud.current().owner
        state = cloud.states.get(owner, {})
        if state.get("kind") != "limited":
            state["retry_at"] = 0
        cloud.wake.set()
        return redirect(url_for("accounts.settings"), code=303)

    @bp.get("/api/account/status")
    def status():
        value = cloud.status()
        value["message"] = t(value["message"])
        value["label"] = t(value["label"])
        value["sharing"]["label"] = t(sharing_label(value["sharing"]))
        value["sharing"]["badge"] = t(sharing_badge(value["sharing"]))
        return jsonify(value)

    @bp.post("/account/adopt-local")
    def adopt_local():
        library = cloud.current()
        if not library.owner or request.form.get("confirm") != "yes":
            abort(400)
        try:
            count, skipped = library.store.copy_from(cloud.guest)
        except (sqlite3.Error, OSError):
            return page(
                "Could not copy your local library. Your saved films are unchanged. Please try again.",
                flow="settings",
            ), 503
        cloud.wake.set()
        flash(
            t(
                "{count} films imported. {skipped} existing records were kept.",
                count=count,
                skipped=skipped,
            )
        )
        if skipped:
            flash(
                "Films already in your account kept their notes and ratings. The other versions remain in your original local library."
            )
        return redirect(url_for("accounts.settings"), code=303)

    @bp.post("/account/resolve")
    def resolve():
        try:
            cloud.current().store.resolve(
                request.form.get("record_key", ""),
                request.form.get("choice"),
                int(request.form.get("revision", "")),
            )
            flash("Conflict resolved. Earlier versions remain in your library export.")
            return redirect(url_for("accounts.settings") + "#conflicts", code=303)
        except (ValueError, TypeError) as error:
            return page(error, flow="settings"), 409

    @bp.get("/account/export")
    def export():
        payload = json.dumps(
            cloud.current().store.export(), ensure_ascii=False, indent=2
        ).encode("utf-8")
        return send_file(
            BytesIO(payload),
            mimetype="application/json",
            as_attachment=True,
            download_name=f"MyMovieList-library-{datetime.now(timezone.utc).date().isoformat()}.json",
        )

    @bp.post("/account/import")
    def import_library():
        try:
            uploaded = request.files.get("library_file")
            if not uploaded:
                raise ValueError("Choose a MyMovieList library export.")
            raw = uploaded.read(50 * 1024 * 1024 + 1)
            if len(raw) > 50 * 1024 * 1024:
                raise ValueError("Choose an export under 50 MB.")
            count, skipped = cloud.current().store.import_new(json.loads(raw))
            flash(
                t(
                    "{count} films imported. {skipped} existing records were kept.",
                    count=count,
                    skipped=skipped,
                )
            )
            return redirect(url_for("settings") + "#backup", code=303)
        except (ValueError, UnicodeError) as error:
            return page(
                str(error)
                if not isinstance(error, json.JSONDecodeError)
                else "Choose a valid library export."
            ), 422

    @app.errorhandler(CloudError)
    def cloud_error(error):
        if request.headers.get("Accept") == "application/json":
            return jsonify(error=t(str(error))), 503
        return page(error), 503

    app.register_blueprint(bp)
