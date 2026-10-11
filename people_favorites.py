"""Private, account-scoped person preferences with durable offline operations."""

import json
import re
from uuid import uuid4

from field_sync import clock_now, observe
from personal_data import timestamp

ROLES = ("actor", "director")
FIELDS = {"person_id", "role", "favorite", "edited_at"}


def validate(value):
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError("Invalid person favorite.")
    if (
        type(value["person_id"]) is not int
        or not 1 <= value["person_id"] <= 9999999999
        or value["role"] not in ROLES
        or type(value["favorite"]) is not bool
    ):
        raise ValueError("Invalid person favorite.")
    return {**value, "edited_at": timestamp(value["edited_at"])}


def validate_export(value):
    if not isinstance(value, list) or len(value) > 10000:
        raise ValueError("Invalid person favorites export.")
    records = [validate(row) for row in value]
    if len({(r["role"], r["person_id"]) for r in records}) != len(records):
        raise ValueError("Duplicate person favorite.")
    return records


def create_tables(con):
    con.execute("""CREATE TABLE IF NOT EXISTS person_favorites (
        role TEXT NOT NULL, person_id INTEGER NOT NULL, favorite INTEGER NOT NULL,
        edited_at TEXT NOT NULL, baseline TEXT, revision INTEGER NOT NULL DEFAULT 0,
        outbox TEXT, PRIMARY KEY(role,person_id))""")
    con.execute("""CREATE TABLE IF NOT EXISTS person_metadata (
        person_id INTEGER NOT NULL, locale TEXT NOT NULL, data_json TEXT NOT NULL,
        PRIMARY KEY(person_id,locale))""")


def record(row):
    return {
        "person_id": row["person_id"],
        "role": row["role"],
        "favorite": bool(row["favorite"]),
        "edited_at": row["edited_at"],
    }


def export(con):
    return [
        record(r)
        for r in con.execute("SELECT * FROM person_favorites ORDER BY role,person_id")
    ]


def import_new(con, rows):
    known = {
        (r["role"], r["person_id"])
        for r in con.execute("SELECT role,person_id FROM person_favorites")
    }
    if len(known | {(r["role"], r["person_id"]) for r in rows}) > 10000:
        raise ValueError("Your person favorites list is full.")
    for row in rows:
        con.execute(
            """INSERT OR IGNORE INTO person_favorites
            (role,person_id,favorite,edited_at) VALUES (?,?,?,?)""",
            (row["role"], row["person_id"], row["favorite"], row["edited_at"]),
        )


class PersonFavorites:
    def __init__(self, db):
        self.db = db

    def keys(self):
        return {
            f"{r['role']}:{r['person_id']}"
            for r in self.db.query(
                "SELECT role,person_id FROM person_favorites WHERE favorite=1"
            )
        }

    def set(self, person_id, role, favorite):
        if (
            type(person_id) is not int
            or not 1 <= person_id <= 9999999999
            or role not in ROLES
            or type(favorite) is not bool
        ):
            raise ValueError("Invalid person favorite.")
        with self.db.connect(write=True) as con:
            old = con.execute(
                "SELECT * FROM person_favorites WHERE role=? AND person_id=?",
                (role, person_id),
            ).fetchone()
            if old and bool(old["favorite"]) == favorite:
                return
            if (
                not old
                and con.execute("SELECT count(*) FROM person_favorites").fetchone()[0]
                >= 10000
            ):
                raise ValueError("Your person favorites list is full.")
            con.execute(
                """INSERT INTO person_favorites(role,person_id,favorite,edited_at)
                VALUES (?,?,?,?) ON CONFLICT(role,person_id) DO UPDATE SET
                favorite=excluded.favorite, edited_at=excluded.edited_at""",
                (role, person_id, favorite, clock_now(con)),
            )

    def pending(self):
        return sum(
            bool(r["outbox"]) or record(r) != json.loads(r["baseline"] or "null")
            for r in self.db.query("SELECT * FROM person_favorites")
        )

    def next_operation(self):
        with self.db.connect(write=True) as con:
            for row in con.execute(
                "SELECT * FROM person_favorites ORDER BY role,person_id"
            ).fetchall():
                if row["outbox"]:
                    return json.loads(row["outbox"])
                value = record(row)
                if value != json.loads(row["baseline"] or "null"):
                    operation = {"operation_id": str(uuid4()), **value}
                    con.execute(
                        "UPDATE person_favorites SET outbox=? WHERE role=? AND person_id=?",
                        (json.dumps(operation), row["role"], row["person_id"]),
                    )
                    return operation

    @staticmethod
    def receive(con, remote, *, acknowledgement=False):
        value = validate({k: v for k, v in remote.items() if k != "revision"})
        revision = remote.get("revision")
        if type(revision) is not int or revision < 1:
            raise ValueError("Invalid person favorite revision.")
        row = con.execute(
            "SELECT * FROM person_favorites WHERE role=? AND person_id=?",
            (value["role"], value["person_id"]),
        ).fetchone()
        if row and (
            row["revision"] > revision
            or row["revision"] == revision
            and not acknowledgement
        ):
            return
        if row and row["outbox"]:
            raise ValueError("Upload queued favorites before receiving changes.")
        chosen = record(row) if row and row["edited_at"] > value["edited_at"] else value
        con.execute(
            """INSERT INTO person_favorites(role,person_id,favorite,edited_at,baseline,revision)
            VALUES (?,?,?,?,?,?) ON CONFLICT(role,person_id) DO UPDATE SET
            favorite=excluded.favorite,edited_at=excluded.edited_at,
            baseline=excluded.baseline,revision=excluded.revision""",
            (
                chosen["role"],
                chosen["person_id"],
                chosen["favorite"],
                chosen["edited_at"],
                json.dumps(value),
                revision,
            ),
        )
        observe(con, {"favorite": value["edited_at"]})

    def acknowledge(self, operation, reply):
        remote = reply.get("record", {})
        if reply.get("status") != "applied" or any(
            remote.get(k) != operation[k] for k in ("role", "person_id")
        ):
            raise ValueError("Invalid person favorite acknowledgement.")
        # Validate before touching the frozen upload; a failed transaction retains it.
        validate({k: v for k, v in remote.items() if k != "revision"})
        with self.db.connect(write=True) as con:
            row = con.execute(
                "SELECT outbox FROM person_favorites WHERE role=? AND person_id=?",
                (operation["role"], operation["person_id"]),
            ).fetchone()
            if not row or json.loads(row[0] or "null") != operation:
                raise ValueError("Person favorite operation changed.")
            con.execute(
                "UPDATE person_favorites SET outbox=NULL WHERE role=? AND person_id=?",
                (operation["role"], operation["person_id"]),
            )
            self.receive(con, remote, acknowledgement=True)

    def cursor(self):
        rows = self.db.query(
            "SELECT value FROM settings WHERE key='people_sync_cursor'"
        )
        return int(rows[0]["value"]) if rows else 0

    def apply_page(self, page):
        if (
            page.get("protocol") != 1
            or not isinstance(page.get("changes"), list)
            or len(page["changes"]) > 100
        ):
            raise ValueError("Invalid person favorites page.")
        with self.db.connect(write=True) as con:
            row = con.execute(
                "SELECT value FROM settings WHERE key='people_sync_cursor'"
            ).fetchone()
            previous = int(row[0]) if row else 0
            for remote in page["changes"]:
                revision = remote.get("revision")
                if type(revision) is not int or revision <= previous:
                    raise ValueError("Invalid person favorites cursor.")
                self.receive(con, remote)
                previous = revision
            if type(page.get("cursor")) is not int or page["cursor"] != previous:
                raise ValueError("Invalid person favorites cursor.")
            con.execute(
                "INSERT OR REPLACE INTO settings VALUES ('people_sync_cursor',?)",
                (str(previous),),
            )

    def cache(self, person_id, value, locale="en"):
        if (
            type(person_id) is not int
            or not 1 <= person_id <= 9999999999
            or locale not in ("en", "tr")
        ):
            raise ValueError("Invalid person identity.")
        if value.get("id", person_id) != person_id:
            raise ValueError("Invalid person identity.")
        data = {k: v for k, v in value.items() if k != "portrait_url"}
        data["id"] = person_id
        data["name"] = str(data.get("name") or f"TMDB #{person_id}")[:200]
        path = data.get("profile_path")
        if not path and isinstance(value.get("portrait_url"), str):
            path = value["portrait_url"].removeprefix("https://image.tmdb.org/t/p/w185")
        data["profile_path"] = (
            path
            if isinstance(path, str)
            and re.fullmatch(r"/[A-Za-z0-9_-]+\.(jpg|jpeg|png|webp)", path)
            else None
        )
        encoded = json.dumps(data, ensure_ascii=False)
        if len(encoded.encode()) > 1024 * 1024:
            return
        with self.db.connect(write=True) as con:
            old = con.execute(
                "SELECT data_json FROM person_metadata WHERE person_id=? AND locale=?",
                (person_id, locale),
            ).fetchone()
            if old:
                data = {**json.loads(old[0]), **data}
            con.execute(
                "INSERT OR REPLACE INTO person_metadata VALUES (?,?,?)",
                (person_id, locale, json.dumps(data, ensure_ascii=False)),
            )

    def metadata(self, person_id, locale="en"):
        rows = self.db.query(
            "SELECT data_json FROM person_metadata WHERE person_id=? ORDER BY locale=? DESC LIMIT 1",
            person_id,
            locale,
        )
        return json.loads(rows[0]["data_json"]) if rows else None

    def listing(self, role, locale="en", page=1):
        if role not in ROLES:
            raise ValueError("Invalid favorite role.")
        count = self.db.query(
            "SELECT count(*) n FROM person_favorites WHERE favorite=1 AND role=?", role
        )[0]["n"]
        rows = self.db.query(
            "SELECT person_id FROM person_favorites WHERE favorite=1 AND role=? ORDER BY edited_at DESC,person_id LIMIT 24 OFFSET ?",
            role,
            (page - 1) * 24,
        )
        return count, [
            dict(
                self.metadata(r["person_id"], locale)
                or {"id": r["person_id"], "name": f"TMDB #{r['person_id']}"},
                favorite_role=role,
            )
            for r in rows
        ]
