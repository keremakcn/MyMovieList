"""Atomic local queue, server baselines and recoverable personal-data conflicts."""

import json
import time
from uuid import UUID, uuid4

from personal_data import dumps, from_movie, three_way, timestamp, validate_record
from storage import utcnow


def create_tables(con):
    con.execute("""CREATE TABLE IF NOT EXISTS sync_baselines (
        record_key TEXT PRIMARY KEY, revision INTEGER NOT NULL, data_json TEXT NOT NULL)""")
    con.execute("CREATE TABLE IF NOT EXISTS sync_dirty (record_key TEXT PRIMARY KEY)")
    con.execute("""CREATE TABLE IF NOT EXISTS sync_outbox (
        record_key TEXT PRIMARY KEY, operation_id TEXT NOT NULL UNIQUE,
        expected_revision INTEGER NOT NULL, data_json TEXT NOT NULL)""")
    con.execute("""CREATE TABLE IF NOT EXISTS sync_conflicts (
        record_key TEXT PRIMARY KEY, remote_revision INTEGER NOT NULL,
        local_json TEXT NOT NULL, remote_json TEXT NOT NULL)""")
    con.execute("""CREATE TABLE IF NOT EXISTS sync_conflict_archive (
        id TEXT PRIMARY KEY, record_key TEXT NOT NULL, local_json TEXT NOT NULL,
        remote_json TEXT NOT NULL, remote_revision INTEGER NOT NULL, created_at TEXT NOT NULL)""")


def track_movie(con, movie_id, *, queue):
    row = con.execute("SELECT * FROM movies WHERE id=?", (movie_id,)).fetchone()
    if row is None:
        return
    if not row["record_key"]:
        suffix = str(uuid4())
        key = f"tmdb:{row['tmdb_id']}" if row["tmdb_id"] else f"custom:{suffix}"
        con.execute(
            "UPDATE movies SET record_key=?,order_key=?,sync_added_at=? WHERE id=?",
            (
                key,
                f"{time.time_ns() // 1000:020}:{suffix}",
                row["created_at"] or utcnow(),
                movie_id,
            ),
        )
    if queue:
        key = con.execute(
            "SELECT record_key FROM movies WHERE id=?", (movie_id,)
        ).fetchone()[0]
        con.execute("INSERT OR IGNORE INTO sync_dirty(record_key) VALUES (?)", (key,))


class SyncStore:
    def __init__(self, db):
        self.db = db

    def export(self):
        with self.db.connect() as con:
            con.execute("BEGIN")
            return self._export(con)

    @staticmethod
    def _export(con):
        records = [
            {"record_key": r["record_key"], "data": from_movie(dict(r))}
            for r in con.execute("SELECT * FROM movies ORDER BY order_key")
        ]
        archived = [
            dict(r)
            for r in con.execute(
                "SELECT * FROM sync_conflict_archive ORDER BY created_at"
            )
        ]
        return {
            "format": "mymovielist-personal-library",
            "version": 1,
            "exported_at": utcnow(),
            "records": records,
            "conflict_versions": archived,
        }

    def copy_from(self, source):
        """Copy a device library without replacing an existing account record."""
        # One read snapshot keeps notes, ordering and offline details consistent
        # even if another request edits the source during the copy.
        with source.connect() as con:
            con.execute("BEGIN")
            document = self._export(con)
            rows = [dict(row) for row in con.execute("SELECT * FROM movies")]
            metadata = [
                tuple(row)
                for row in con.execute(
                    "SELECT tmdb_id,english_title,original_title,turkish_title,data_json,fetched_at "
                    "FROM movie_metadata"
                )
            ]
        return self.import_new(document, _catalog_snapshot=(rows, metadata))

    def import_new(self, document, *, _catalog_snapshot=None):
        if (
            not isinstance(document, dict)
            or document.get("format") != "mymovielist-personal-library"
            or document.get("version") != 1
        ):
            raise ValueError("Choose a supported MyMovieList library export.")
        records = document.get("records")
        if not isinstance(records, list) or len(records) > 10000:
            raise ValueError("An import can contain up to 10,000 films.")
        validated = []
        for r in records:
            if not isinstance(r, dict) or set(r) != {"record_key", "data"}:
                raise ValueError("Invalid personal record.")
            validated.append(
                (r["record_key"], validate_record(r["record_key"], r["data"]))
            )
        archives = document.get("conflict_versions", [])
        if not isinstance(archives, list) or len(archives) > 50000:
            raise ValueError("Invalid conflict history.")
        validated_archives = []
        for r in archives:
            if not isinstance(r, dict) or set(r) != {
                "id",
                "record_key",
                "local_json",
                "remote_json",
                "remote_revision",
                "created_at",
            }:
                raise ValueError("Invalid conflict history.")
            if type(r["remote_revision"]) is not int or r["remote_revision"] < 1:
                raise ValueError("Invalid conflict revision.")
            if any(
                not isinstance(r[name], str)
                for name in ("id", "local_json", "remote_json", "created_at")
            ):
                raise ValueError("Invalid conflict history.")
            validated_archives.append(
                (
                    str(UUID(r["id"])),
                    r["record_key"],
                    dumps(
                        validate_record(r["record_key"], json.loads(r["local_json"]))
                    ),
                    dumps(
                        validate_record(r["record_key"], json.loads(r["remote_json"]))
                    ),
                    r["remote_revision"],
                    timestamp(r["created_at"]),
                )
            )
        catalog_rows, metadata = _catalog_snapshot or ([], [])
        imported = skipped = 0
        new_keys = set()
        with self.db.connect(write=True) as con:
            for key, data in validated:
                if con.execute(
                    "SELECT 1 FROM movies WHERE record_key=?", (key,)
                ).fetchone():
                    skipped += 1
                    continue
                self._apply(con, key, data)
                if self.db.owner_id:
                    con.execute("INSERT OR IGNORE INTO sync_dirty VALUES (?)", (key,))
                imported += 1
                new_keys.add(key)
            con.executemany(
                "INSERT OR IGNORE INTO sync_conflict_archive VALUES (?,?,?,?,?,?)",
                validated_archives,
            )
            # Personal records and their available offline details commit together.
            # Existing account notes/ratings are retained; the original source is untouched.
            for row in catalog_rows:
                key = row["record_key"]
                if key in new_keys:
                    con.execute(
                        "UPDATE movies SET created_at=?,updated_at=COALESCE(?,updated_at) "
                        "WHERE record_key=?",
                        (row["created_at"], row["updated_at"], key),
                    )
                if not row["tmdb_id"]:
                    continue
                for name in (
                    "poster_path",
                    "overview",
                    "runtime",
                    "director",
                    "cast_list",
                    "score_percent",
                    "entities_json",
                    "genre",
                    "year",
                ):
                    if row.get(name) is not None:
                        con.execute(
                            f"UPDATE movies SET {name}=COALESCE({name},?) WHERE record_key=?",
                            (row[name], key),
                        )
                con.execute(
                    "UPDATE movies SET title=?,catalog_pending=? "
                    "WHERE record_key=? AND catalog_pending=1",
                    (row["title"], row["catalog_pending"], key),
                )
            con.executemany(
                "INSERT OR IGNORE INTO movie_metadata "
                "(tmdb_id,english_title,original_title,turkish_title,data_json,fetched_at) "
                "VALUES (?,?,?,?,?,?)",
                metadata,
            )
        return imported, skipped

    @staticmethod
    def _apply(con, key, data):
        row = con.execute("SELECT * FROM movies WHERE record_key=?", (key,)).fetchone()
        values = {
            "status": data["status"],
            "rating": data["rating"],
            "note": data["note"],
            "favorite": int(data["favorite"]),
            "watched_date": data["watched_date"],
            "sync_added_at": data["added_at"],
            "order_key": data["order_key"],
            "deleted_at": data["deleted_at"],
        }
        if data["custom"] is not None:
            values.update(data["custom"])
        if row:
            con.execute(
                "UPDATE movies SET "
                + ",".join(k + "=?" for k in values)
                + " WHERE id=?",
                (*values.values(), row["id"]),
            )
        else:
            mid = int(key.split(":")[1]) if key.startswith("tmdb:") else None
            # A stable ID placeholder is safe offline; catalog hydration replaces
            # public details when available without using titles as identity.
            values.update(
                record_key=key,
                tmdb_id=mid,
                created_at=data["added_at"],
                updated_at=utcnow(),
            )
            values["catalog_pending"] = int(mid is not None)
            values.setdefault("title", f"TMDB #{mid}")
            con.execute(
                "INSERT INTO movies ("
                + ",".join(values)
                + ") VALUES ("
                + ",".join("?" for _ in values)
                + ")",
                tuple(values.values()),
            )

    def next_operation(self):
        with self.db.connect(write=True) as con:
            row = con.execute(
                "SELECT * FROM sync_outbox ORDER BY rowid LIMIT 1"
            ).fetchone()
            if row:
                return dict(row)
            dirty = con.execute("""SELECT d.record_key FROM sync_dirty d
                LEFT JOIN sync_conflicts c ON c.record_key=d.record_key
                WHERE c.record_key IS NULL ORDER BY d.rowid LIMIT 1""").fetchone()
            if dirty is None:
                return None
            key = dirty["record_key"]
            movie = con.execute(
                "SELECT * FROM movies WHERE record_key=?", (key,)
            ).fetchone()
            baseline = con.execute(
                "SELECT revision FROM sync_baselines WHERE record_key=?", (key,)
            ).fetchone()
            operation = {
                "record_key": key,
                "operation_id": str(uuid4()),
                "expected_revision": baseline["revision"] if baseline else 0,
                "data_json": dumps(from_movie(dict(movie))),
            }
            con.execute(
                "INSERT INTO sync_outbox VALUES (?,?,?,?)",
                tuple(
                    operation[k]
                    for k in (
                        "record_key",
                        "operation_id",
                        "expected_revision",
                        "data_json",
                    )
                ),
            )
            con.execute("DELETE FROM sync_dirty WHERE record_key=?", (key,))
            return operation

    def acknowledge(self, operation, revision):
        if type(revision) is not int or revision <= operation["expected_revision"]:
            raise ValueError("Invalid synchronization acknowledgement.")
        with self.db.connect(write=True) as con:
            current = con.execute(
                "SELECT operation_id FROM sync_outbox WHERE record_key=?",
                (operation["record_key"],),
            ).fetchone()
            if not current or current["operation_id"] != operation["operation_id"]:
                raise ValueError("The queued operation changed.")
            con.execute(
                "INSERT OR REPLACE INTO sync_baselines VALUES (?,?,?)",
                (operation["record_key"], revision, operation["data_json"]),
            )
            con.execute(
                "DELETE FROM sync_outbox WHERE operation_id=?",
                (operation["operation_id"],),
            )

    def reject_conflict(self, operation, remote):
        if (
            type(remote.get("revision")) is not int
            or remote["revision"] <= operation["expected_revision"]
        ):
            raise ValueError("Invalid remote revision.")
        with self.db.connect(write=True) as con:
            con.execute(
                "DELETE FROM sync_outbox WHERE operation_id=?",
                (operation["operation_id"],),
            )
            con.execute(
                "INSERT OR IGNORE INTO sync_dirty VALUES (?)",
                (operation["record_key"],),
            )
            self._merge(
                con, operation["record_key"], remote["revision"], remote["data"]
            )

    def _merge(self, con, key, revision, data):
        data = validate_record(key, data)
        baseline = con.execute(
            "SELECT * FROM sync_baselines WHERE record_key=?", (key,)
        ).fetchone()
        if baseline and baseline["revision"] >= revision:
            return
        row = con.execute("SELECT * FROM movies WHERE record_key=?", (key,)).fetchone()
        dirty = con.execute(
            "SELECT 1 FROM sync_dirty WHERE record_key=?", (key,)
        ).fetchone()
        conflict = con.execute(
            "SELECT 1 FROM sync_conflicts WHERE record_key=?", (key,)
        ).fetchone()
        local = from_movie(dict(row)) if row else None
        merged, competing = (data, False)
        if row and (dirty or conflict):
            merged, competing = three_way(
                json.loads(baseline["data_json"]) if baseline else None, local, data
            )
        if competing:
            con.execute(
                "INSERT OR REPLACE INTO sync_conflicts VALUES (?,?,?,?)",
                (key, revision, dumps(local), dumps(data)),
            )
            con.execute(
                "INSERT INTO sync_conflict_archive VALUES (?,?,?,?,?,?)",
                (str(uuid4()), key, dumps(local), dumps(data), revision, utcnow()),
            )
        else:
            self._apply(con, key, merged)
            con.execute("DELETE FROM sync_conflicts WHERE record_key=?", (key,))
            con.execute("DELETE FROM sync_dirty WHERE record_key=?", (key,))
            if merged != data and self.db.owner_id:
                con.execute("INSERT INTO sync_dirty VALUES (?)", (key,))
        con.execute(
            "INSERT OR REPLACE INTO sync_baselines VALUES (?,?,?)",
            (key, revision, dumps(data)),
        )

    def apply_page(self, page):
        if (
            type(page.get("protocol")) is not int
            or page.get("protocol") != 1
            or not isinstance(page.get("changes"), list)
            or len(page["changes"]) > 200
        ):
            raise ValueError("Invalid synchronization page.")
        with self.db.connect(write=True) as con:
            old = self.cursor(con)
            previous = old
            for change in page["changes"]:
                revision = change.get("revision")
                if type(revision) is not int or revision <= previous:
                    raise ValueError("Synchronization revisions are out of order.")
                previous = revision
                if con.execute(
                    "SELECT 1 FROM sync_outbox WHERE record_key=?",
                    (change["record_key"],),
                ).fetchone():
                    raise ValueError("Push pending operations before pulling changes.")
                self._merge(con, change["record_key"], revision, change["data"])
            if page.get("cursor") != previous:
                raise ValueError("Invalid synchronization cursor.")
            con.execute(
                "INSERT OR REPLACE INTO settings VALUES ('sync_cursor',?)",
                (str(previous),),
            )

    def cursor(self, con=None):
        if con is None:
            with self.db.connect() as connection:
                return self.cursor(connection)
        row = con.execute(
            "SELECT value FROM settings WHERE key='sync_cursor'"
        ).fetchone()
        return int(row[0]) if row else 0

    def resolve(self, key, choice, expected_revision):
        if choice not in ("local", "remote"):
            raise ValueError("Choose which version to keep.")
        with self.db.connect(write=True) as con:
            conflict = con.execute(
                "SELECT * FROM sync_conflicts WHERE record_key=?", (key,)
            ).fetchone()
            if not conflict or conflict["remote_revision"] != expected_revision:
                raise ValueError(
                    "This conflict changed. Refresh the page before choosing."
                )
            remote = json.loads(conflict["remote_json"])
            row = con.execute(
                "SELECT * FROM movies WHERE record_key=?", (key,)
            ).fetchone()
            local = from_movie(dict(row))
            # Preserve the latest local draft as well as both earlier versions.
            con.execute(
                "INSERT INTO sync_conflict_archive VALUES (?,?,?,?,?,?)",
                (
                    str(uuid4()),
                    key,
                    dumps(local),
                    dumps(remote),
                    expected_revision,
                    utcnow(),
                ),
            )
            selected = local if choice == "local" else remote
            for name in ("added_at", "order_key"):
                selected[name] = remote[name]
            self._apply(con, key, selected)
            con.execute("DELETE FROM sync_conflicts WHERE record_key=?", (key,))
            con.execute("DELETE FROM sync_dirty WHERE record_key=?", (key,))
            if choice == "local":
                con.execute("INSERT INTO sync_dirty VALUES (?)", (key,))

    def pending(self):
        return self.db.query("""SELECT COUNT(*) count FROM (
            SELECT record_key FROM sync_dirty UNION SELECT record_key FROM sync_outbox)""")[
            0
        ]["count"]
