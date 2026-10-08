"""Small private profile metadata; avatar files are shipped with the app."""

import json
import unicodedata
from uuid import uuid4

from personal_data import KEY

AVATARS = (
    ("cat-luna", "Luna"),
    ("cat-cocoa", "Cocoa"),
    ("cat-sunshine", "Sunshine"),
    ("cat-sage", "Sage"),
    ("cat-coral", "Coral"),
    ("cat-cloud", "Cloud"),
    ("cat-midnight", "Midnight"),
    ("cat-peach", "Peach"),
    ("cat-sky", "Sky"),
    ("cat-mocha", "Mocha"),
    ("cat-lilac", "Lilac"),
    ("cat-mint", "Mint"),
    ("cat-cherry", "Cherry"),
    ("cat-gold", "Gold"),
    ("cat-ocean", "Ocean"),
    ("cat-silver", "Silver"),
)
AVATAR_IDS = frozenset(key for key, _ in AVATARS)
DEFAULT_PROFILE = {"display_name": "", "avatar_id": "cat-luna"}
SHOWCASE_LIMIT = 6


def validate_showcase(value):
    if not isinstance(value, dict) or set(value) != {
        "record_keys",
        "show_ratings",
        "show_stats",
    }:
        raise ValueError("Choose valid showcase settings.")
    keys = value["record_keys"]
    if not isinstance(keys, list) or len(keys) > SHOWCASE_LIMIT:
        raise ValueError("Choose up to 6 films for your showcase.")
    if any(not isinstance(key, str) or not KEY.fullmatch(key) for key in keys):
        raise ValueError("Choose films from your current library.")
    if len(set(keys)) != len(keys):
        raise ValueError("Each film can appear only once in your showcase.")
    if any(type(value[field]) is not bool for field in ("show_ratings", "show_stats")):
        raise ValueError("Choose valid showcase settings.")
    return dict(value, record_keys=list(keys))


def showcase_settings(profile):
    return validate_showcase(
        profile.get(
            "showcase",
            {
                "record_keys": [],
                "show_ratings": False,
                "show_stats": False,
            },
        )
    )


def validate_profile(value):
    if not isinstance(value, dict):
        raise TypeError("Choose a valid profile.")
    name = value.get("display_name", "")
    avatar = value.get("avatar_id", "cat-luna")
    if not isinstance(name, str):
        raise TypeError("Use a display name of up to 40 characters.")
    name = unicodedata.normalize("NFC", name.strip())
    if len(name) > 40 or any(unicodedata.category(c).startswith("C") for c in name):
        raise ValueError("Use a display name of up to 40 characters.")
    if not isinstance(avatar, str) or avatar not in AVATAR_IDS:
        raise ValueError("Choose one of the available avatars.")
    result = {"display_name": name, "avatar_id": avatar}
    # Missing in older profiles: start empty, never infer picks from favorites.
    if "showcase" in value:
        result["showcase"] = validate_showcase(value["showcase"])
    return result


def remote_profile(metadata):
    value = metadata.get("mml_profile") if isinstance(metadata, dict) else None
    if not isinstance(value, dict):
        return dict(DEFAULT_PROFILE)
    # Future avatar IDs fall back locally, without rewriting the remote choice.
    try:
        return validate_profile(
            dict(
                value,
                avatar_id=value.get("avatar_id")
                if value.get("avatar_id") in AVATAR_IDS
                else "cat-luna",
            )
        )
    except (ValueError, TypeError):
        # Invalid showcase data must not discard an otherwise valid identity.
        try:
            return validate_profile(
                {
                    "display_name": value.get("display_name", ""),
                    "avatar_id": value.get("avatar_id")
                    if value.get("avatar_id") in AVATAR_IDS
                    else "cat-luna",
                }
            )
        except (ValueError, TypeError):
            return dict(DEFAULT_PROFILE)


class ProfileStore:
    def __init__(self, db):
        self.db = db

    def snapshot(self):
        rows = self.db.query("SELECT value FROM settings WHERE key='account_profile'")
        try:
            value = json.loads(rows[0]["value"]) if rows else {}
            return {
                "profile": validate_profile(value.get("profile", DEFAULT_PROFILE)),
                "dirty": bool(value.get("dirty")),
                "generation": value.get("generation", ""),
            }
        except (ValueError, TypeError, KeyError):
            return {"profile": dict(DEFAULT_PROFILE), "dirty": False, "generation": ""}

    def _write(self, con, value):
        con.execute(
            "INSERT OR REPLACE INTO settings VALUES ('account_profile',?)",
            (json.dumps(value, ensure_ascii=False),),
        )

    def save(self, value):
        if not isinstance(value, dict):
            raise TypeError("Choose a valid profile.")
        with self.db.connect(write=True) as con:
            # Merge inside the write lock: identity and showcase edits from two
            # open screens must not erase each other or a newer queued edit.
            row = con.execute(
                "SELECT value FROM settings WHERE key='account_profile'"
            ).fetchone()
            try:
                current = json.loads(row[0]) if row else {}
            except (ValueError, TypeError):
                current = {}
            previous = (
                remote_profile({"mml_profile": current.get("profile")})
                if isinstance(current, dict)
                else dict(DEFAULT_PROFILE)
            )
            merged = validate_profile(dict(previous, **value))
            if "showcase" in value:
                keys = set(merged["showcase"]["record_keys"])
                existing = set(showcase_settings(previous)["record_keys"])
                if keys:
                    found = {
                        row[0]
                        for row in con.execute(
                            "SELECT record_key FROM movies WHERE deleted_at IS NULL AND record_key IN ("
                            + ",".join("?" for _ in keys)
                            + ")",
                            tuple(keys),
                        )
                    }
                    if keys - found - existing:
                        raise ValueError("Choose films from your current library.")
            self._write(
                con, {"profile": merged, "dirty": True, "generation": uuid4().hex}
            )
        return merged

    def receive(self, value, generation=None):
        value = validate_profile(value)
        with self.db.connect(write=True) as con:
            row = con.execute(
                "SELECT value FROM settings WHERE key='account_profile'"
            ).fetchone()
            current = json.loads(row[0]) if row else {}
            if generation is None and current.get("dirty"):
                return False
            if generation is not None and current.get("generation") != generation:
                return False
            self._write(
                con, {"profile": value, "dirty": False, "generation": uuid4().hex}
            )
            return True
