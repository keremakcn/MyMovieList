"""Explicit publication consent, separate from private profile/library sync."""

import json
from uuid import UUID, uuid4

from account_profile import AVATAR_IDS, showcase_settings, validate_profile
from account_username import normalize_username

PUBLIC_ORIGIN = "https://profiles.myshelf.cloud"
PRIVATE_SETTINGS = {"share_id": None, "is_public": False, "revision": 0}


def validate_settings(value):
    if not isinstance(value, dict) or set(value) != set(PRIVATE_SETTINGS):
        raise ValueError("Invalid sharing response.")
    if (
        type(value["is_public"]) is not bool
        or type(value["revision"]) is not int
        or value["revision"] < 0
    ):
        raise ValueError("Invalid sharing response.")
    share_id = value["share_id"]
    if share_id is not None:
        share_id = str(UUID(share_id))
    elif value["is_public"] or value["revision"]:
        raise ValueError("Invalid sharing response.")
    return dict(value, share_id=share_id)


def validate_public_profile(value):
    """Accept a strict public DTO, never arbitrary private provider fields."""
    if not isinstance(value, dict) or type(value.get("found")) is not bool:
        raise ValueError("Invalid public profile.")
    if not value["found"]:
        if set(value) != {"found"}:
            raise ValueError("Invalid public profile.")
        return {"found": False}
    fields = {"found", "share_id", "display_name", "avatar_id", "films"}
    if "username" in value:
        fields.add("username")
        if normalize_username(value["username"]) != value["username"]:
            raise ValueError("Invalid public profile.")
    if set(value) not in (fields, fields | {"counts"}):
        raise ValueError("Invalid public profile.")
    identity = validate_profile(
        {key: value[key] for key in ("display_name", "avatar_id")}
    )
    if (
        not isinstance(value["avatar_id"], str)
        or value["avatar_id"] not in AVATAR_IDS
        or not isinstance(value["films"], list)
        or len(value["films"]) > 6
    ):
        raise ValueError("Invalid public profile.")
    films, seen = [], set()
    for film in value["films"]:
        if not isinstance(film, dict) or set(film) not in (
            {"tmdb_id"},
            {"tmdb_id", "rating"},
        ):
            raise ValueError("Invalid public film.")
        mid = film["tmdb_id"]
        if type(mid) is not int or not 1 <= mid <= 9_999_999_999 or mid in seen:
            raise ValueError("Invalid public film.")
        if "rating" in film and (
            type(film["rating"]) is not int or not 1 <= film["rating"] <= 10
        ):
            raise ValueError("Invalid public rating.")
        films.append(dict(film))
        seen.add(mid)
    result = dict(
        found=True, share_id=str(UUID(value["share_id"])), films=films, **identity
    )
    if "username" in value:
        result["username"] = value["username"]
    if "counts" in value:
        counts = value["counts"]
        if (
            not isinstance(counts, dict)
            or set(counts) != {"total", "watched", "favorites", "watchlist"}
            or any(type(v) is not int or v < 0 for v in counts.values())
            or counts["watched"] + counts["watchlist"] != counts["total"]
            or counts["favorites"] > counts["total"]
        ):
            raise ValueError("Invalid public counts.")
        result["counts"] = dict(counts)
    return result


class SharingStore:
    def __init__(self, db, ready=False):
        self.db, self.ready = db, ready
        self.next_attempt = 0

    def _read(self, con):
        row = con.execute(
            "SELECT value FROM settings WHERE key='profile_sharing'"
        ).fetchone()
        try:
            value = json.loads(row[0]) if row else {}
            validate_settings(value.get("remote", PRIVATE_SETTINGS))
            if not isinstance(value, dict):
                raise TypeError
            operation = value.get("operation")
            if operation is not None:
                if not isinstance(operation, dict) or set(operation) != {
                    "operation_id",
                    "expected_revision",
                    "action",
                    "payload",
                }:
                    raise ValueError
                UUID(operation["operation_id"])
                if (
                    operation["action"] not in ("publish", "update", "unpublish")
                    or type(operation["expected_revision"]) is not int
                    or operation["expected_revision"] < 0
                    or not isinstance(operation["payload"], dict)
                ):
                    raise ValueError
            return value
        except (TypeError, ValueError, AttributeError, KeyError):
            return {}

    def snapshot(self):
        with self.db.connect() as con:
            return self._read(con)

    @staticmethod
    def _write(con, value):
        con.execute(
            "INSERT OR REPLACE INTO settings VALUES ('profile_sharing',?)",
            (json.dumps(value),),
        )

    def payload(self, profile):
        profile = validate_profile(profile)
        selection = showcase_settings(profile)
        keys = [key for key in selection["record_keys"] if key.startswith("tmdb:")]
        found = (
            {
                row["record_key"]
                for row in self.db.query(
                    "SELECT record_key FROM movies WHERE record_key IN ("
                    + ",".join("?" for _ in keys)
                    + ")",
                    *keys,
                )
            }
            if keys
            else set()
        )
        return {
            "display_name": profile["display_name"],
            "avatar_id": profile["avatar_id"],
            "tmdb_ids": [int(key[5:]) for key in keys if key in found],
            "show_ratings": selection["show_ratings"],
            "show_stats": selection["show_stats"],
        }

    def queue(self, action, profile=None):
        if action not in ("publish", "unpublish", "update"):
            raise ValueError("Choose a valid sharing action.")
        payload = {} if action == "unpublish" else self.payload(profile)
        with self.db.connect(write=True) as con:
            value = self._read(con)
            remote = value.get("remote", PRIVATE_SETTINGS)
            pending = value.get("operation")
            if action == "publish" and pending and pending["action"] == "publish":
                if payload != pending["payload"]:
                    value["followup"] = payload
                    self._write(con, value)
                return
            if action == "update" and pending and pending["action"] == "publish":
                value["followup"] = payload
                self._write(con, value)
                return
            if action == "update" and (
                not remote["is_public"] or pending and pending["action"] != "update"
            ):
                return
            if action == "unpublish":
                value.pop("followup", None)
            value["operation"] = {
                "operation_id": str(uuid4()),
                "expected_revision": remote["revision"],
                "action": action,
                "payload": payload,
            }
            value.pop("error", None)
            self._write(con, value)
        self.next_attempt = 0

    def remote(self, settings):
        settings = validate_settings(settings)
        with self.db.connect(write=True) as con:
            value = self._read(con)
            value.update(remote=settings, checked=True)
            value.pop("error", None)
            self._write(con, value)

    def complete(self, operation, reply):
        if (
            not isinstance(reply, dict)
            or set(reply) != {"status", "settings"}
            or reply["status"] not in ("applied", "conflict")
        ):
            raise ValueError("Invalid sharing response.")
        settings = validate_settings(reply["settings"])
        with self.db.connect(write=True) as con:
            value = self._read(con)
            pending = value.get("operation")
            value.update(remote=settings, checked=True)
            value.pop("error", None)
            if pending and pending["operation_id"] == operation["operation_id"]:
                value.pop("operation", None)
                followup = value.pop("followup", None)
                if followup and reply["status"] == "applied" and settings["is_public"]:
                    value["operation"] = {
                        "operation_id": str(uuid4()),
                        "expected_revision": settings["revision"],
                        "action": "update",
                        "payload": followup,
                    }
                    self.next_attempt = 0
                if reply["status"] == "conflict":
                    value["error"] = "changed"
            elif (
                pending
                and pending["action"] == "update"
                and reply["status"] == "applied"
            ):
                pending["expected_revision"] = settings["revision"]
            self._write(con, value)

    def error(self, kind):
        with self.db.connect(write=True) as con:
            value = self._read(con)
            value["error"] = kind
            self._write(con, value)

    def view(self):
        value = self.snapshot()
        remote = value.get("remote", PRIVATE_SETTINGS)
        action = value.get("operation", {}).get("action")
        error = value.get("error")
        state = action or ("public" if remote["is_public"] else "private")
        if error and not action:
            state = "attention"
        return {
            "state": state,
            "is_public": remote["is_public"],
            "pending": action,
            "checked": bool(value.get("checked")),
            "ready": self.ready,
            "error": error,
            "url": PUBLIC_ORIGIN + "/u/" + remote["share_id"]
            if remote["share_id"]
            else None,
            "share_id": remote["share_id"],
            "revision": remote["revision"],
        }


def sharing_label(view):
    if (not view["ready"] or view["error"] == "setup") and not view["is_public"]:
        return "Public profiles are being prepared. Your showcase stays private."
    if view["pending"] == "unpublish":
        return "Making your profile private… It may remain visible until connected."
    if view["pending"] == "publish":
        return "Publishing your showcase…"
    if view["pending"] == "update":
        return "Updating your public showcase…"
    if view["error"] == "changed":
        return "Sharing changed on another device. Review the current setting."
    if view["error"]:
        return "Could not check sharing. The last confirmed setting is shown."
    if not view["checked"]:
        return "Checking profile sharing…"
    return (
        "Your showcase is public." if view["is_public"] else "Your showcase is private."
    )


def sharing_badge(view):
    if view["is_public"]:
        return "Public showcase"
    if view["pending"] == "publish":
        return "Publishing your showcase…"
    if view["ready"] and not view["checked"] and view["error"] != "setup":
        return "Checking profile sharing…"
    return "Private profile"
