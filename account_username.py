"""Server-owned unique handles, separate from non-unique display names."""

import json
import re

from name_policy import require_allowed_name

USERNAME = re.compile(r"[a-z][a-z0-9_]{2,23}\Z", re.ASCII)
RESERVED = frozenset(
    [
        "admin",
        "administrator",
        "api",
        "auth",
        "support",
        "root",
        "system",
        "myshelf",
        "mymovielist",
        "myserieslist",
        "mygamelist",
        "account",
        "settings",
        "login",
        "logout",
        "register",
        "signup",
        "signin",
        "profile",
        "profiles",
        "help",
        "about",
        "official",
        "null",
        "undefined",
    ]
)
PUBLIC_ORIGIN = "https://myshelf.cloud"


def normalize_username(value, *, writing=False):
    if not isinstance(value, str) or not value.isascii():
        raise ValueError(
            "Use 3–24 letters, numbers or underscores, starting with a letter."
        )
    value = value.strip().lower()
    if not USERNAME.fullmatch(value):
        raise ValueError(
            "Use 3–24 letters, numbers or underscores, starting with a letter."
        )
    if value in RESERVED:
        raise ValueError("This username is reserved. Choose another one.")
    if writing:
        require_allowed_name(value)
    return value


def validate_username_status(value):
    if not isinstance(value, dict) or set(value) != {"username"}:
        raise ValueError("Invalid username response.")
    name = value["username"]
    if name is not None and normalize_username(name) != name:
        raise ValueError("Invalid username response.")
    return dict(value)


class UsernameStore:
    def __init__(self, db, ready=False):
        self.db, self.ready, self.next_attempt = db, ready, 0

    def view(self):
        rows = self.db.query("SELECT value FROM settings WHERE key='account_username'")
        try:
            value = json.loads(rows[0]["value"]) if rows else {}
            name = validate_username_status({"username": value.get("username")})[
                "username"
            ]
            checked, error = bool(value.get("checked")), value.get("error")
        except (TypeError, ValueError, AttributeError):
            name, checked, error = None, False, None
        return {
            "username": name,
            "ready": self.ready,
            "checked": checked,
            "error": error,
            "url": PUBLIC_ORIGIN + "/u/" + name if name else None,
        }

    def receive(self, value):
        value = validate_username_status(value)
        self._write(dict(value, checked=True))

    def error(self, kind):
        current = self.view()
        self._write(
            {
                "username": current["username"],
                "checked": current["checked"],
                "error": kind,
            }
        )

    def _write(self, value):
        # A status request started before a foreground claim may return null
        # afterwards. Handles are immutable: a stale read/error cannot erase a
        # successfully reserved name or temporarily change its public URL.
        with self.db.connect(write=True) as con:
            row = con.execute(
                "SELECT value FROM settings WHERE key='account_username'"
            ).fetchone()
            try:
                current = json.loads(row[0]) if row else {}
                name = validate_username_status({"username": current.get("username")})[
                    "username"
                ]
            except (TypeError, ValueError, AttributeError):
                name = None
            if name:
                if value.get("username") not in (None, name):
                    raise ValueError("Invalid username response.")
                value = dict(value, username=name)
            con.execute(
                "INSERT OR REPLACE INTO settings VALUES ('account_username',?)",
                (json.dumps(value),),
            )
