"""Local persistence. Migrations never discard library records."""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class Database:
    def __init__(self, path):
        self.path = str(path)

    @contextmanager
    def connect(self, write=False):
        con = sqlite3.connect(self.path, timeout=15)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        try:
            if write:
                con.execute("BEGIN IMMEDIATE")
            yield con
            if write:
                con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def query(self, sql, *params):
        with self.connect() as con:
            return [dict(row) for row in con.execute(sql, params)]

    def execute(self, sql, *params):
        with self.connect(write=True) as con:
            return con.execute(sql, params).rowcount

    def migrate(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with self.connect() as con:
            version = con.execute("PRAGMA user_version").fetchone()[0]
            if version > 2:
                raise RuntimeError("This library was created by a newer app version.")
            has_movies = con.execute(
                "SELECT 1 FROM sqlite_master WHERE name='movies'"
            ).fetchone()
            if has_movies and version < 2:
                backup_path = (
                    self.path
                    + ".before-v2-"
                    + datetime.now().strftime("%Y%m%d-%H%M%S")
                    + ".bak"
                )
                with sqlite3.connect(backup_path) as backup:
                    con.backup(backup)
        with self.connect(write=True) as con:
            con.execute("""CREATE TABLE IF NOT EXISTS movies (
                id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
                year INTEGER, genre TEXT, status TEXT NOT NULL DEFAULT 'Watchlist',
                rating INTEGER, note TEXT, favorite INTEGER NOT NULL DEFAULT 0,
                watched_date TEXT, catalog_id INTEGER)""")
            columns = {r["name"] for r in con.execute("PRAGMA table_info(movies)")}
            additions = {
                "tmdb_id": "INTEGER",
                "poster_path": "TEXT",
                "overview": "TEXT",
                "runtime": "INTEGER",
                "director": "TEXT",
                "cast_list": "TEXT",
                "score_percent": "INTEGER",
                "created_at": "TEXT",
                "updated_at": "TEXT",
                "deleted_at": "TEXT",
                "entities_json": "TEXT",
            }
            for column, kind in additions.items():
                if column not in columns:
                    con.execute(f"ALTER TABLE movies ADD COLUMN {column} {kind}")
            # A duplicate must never be "fixed" by deleting someone's notes.
            duplicate = con.execute(
                "SELECT tmdb_id FROM movies WHERE tmdb_id IS NOT NULL GROUP BY tmdb_id HAVING COUNT(*)>1"
            ).fetchone()
            if duplicate:
                raise RuntimeError(
                    "Duplicate TMDB records detected. Migration stopped without deleting records; reconcile the backed-up library first."
                )
            con.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_movies_tmdb_id ON movies(tmdb_id)"
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_movies_active_status ON movies(deleted_at, status, id)"
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_movies_active_favorite ON movies(deleted_at, favorite, id)"
            )
            con.execute(
                "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)"
            )
            con.execute("""CREATE TABLE IF NOT EXISTS recommendation_likes (
                movie_id INTEGER PRIMARY KEY REFERENCES movies(id), created_at TEXT NOT NULL)""")
            con.execute("""CREATE TABLE IF NOT EXISTS recommendation_dismissals (
                tmdb_id INTEGER PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL)""")
            con.execute("PRAGMA user_version=2")

    def movie(self, movie_id, include_deleted=False):
        rows = self.query(
            "SELECT * FROM movies WHERE id=?"
            + ("" if include_deleted else " AND deleted_at IS NULL"),
            movie_id,
        )
        return rows[0] if rows else None

    def membership(self, ids):
        ids = list(dict.fromkeys(ids))
        if not ids:
            return {}
        rows = self.query(
            "SELECT id,tmdb_id,status FROM movies WHERE deleted_at IS NULL AND tmdb_id IN ("
            + ",".join("?" for _ in ids)
            + ")",
            *ids,
        )
        return {row["tmdb_id"]: row for row in rows}

    def add_tmdb(self, values):
        with self.connect(write=True) as con:
            existing = con.execute(
                "SELECT * FROM movies WHERE tmdb_id=?", (values["tmdb_id"],)
            ).fetchone()
            if existing:
                if existing["deleted_at"]:
                    con.execute(
                        "UPDATE movies SET deleted_at=NULL WHERE id=?",
                        (existing["id"],),
                    )
                return existing["id"], False
            values = dict(values, created_at=utcnow(), updated_at=utcnow())
            columns = ",".join(values)
            cur = con.execute(
                f"INSERT INTO movies ({columns}) VALUES ({','.join('?' for _ in values)})",
                tuple(values.values()),
            )
            return cur.lastrowid, True

    def remove(self, movie_id):
        with self.connect(write=True) as con:
            row = con.execute("SELECT * FROM movies WHERE id=?", (movie_id,)).fetchone()
            if not row:
                return None
            marker = row["deleted_at"] or utcnow()
            con.execute("UPDATE movies SET deleted_at=? WHERE id=?", (marker, movie_id))
            return marker

    def restore(self, movie_id, marker=None):
        with self.connect(write=True) as con:
            row = con.execute(
                "SELECT deleted_at FROM movies WHERE id=?", (movie_id,)
            ).fetchone()
            if not row:
                return False
            if row["deleted_at"] is None:
                return True
            # An old toast cannot undo a later, separate deletion.
            if marker and row["deleted_at"] != marker:
                return False
            con.execute("UPDATE movies SET deleted_at=NULL WHERE id=?", (movie_id,))
            return True

    def save_survey(self, entries, mode):
        """Atomic and retry-safe: personal columns on existing movies never change."""
        with self.connect(write=True) as con:
            chosen = []
            created = 0
            for tmdb_id, values in entries:
                row = con.execute(
                    "SELECT id FROM movies WHERE tmdb_id=?", (tmdb_id,)
                ).fetchone()
                if row:
                    movie_id = row["id"]
                    con.execute(
                        "UPDATE movies SET deleted_at=NULL WHERE id=?", (movie_id,)
                    )
                else:
                    values = dict(
                        values,
                        tmdb_id=tmdb_id,
                        status="Watched",
                        created_at=utcnow(),
                        updated_at=utcnow(),
                    )
                    columns = ",".join(values)
                    cur = con.execute(
                        f"INSERT INTO movies ({columns}) VALUES ({','.join('?' for _ in values)})",
                        tuple(values.values()),
                    )
                    movie_id = cur.lastrowid
                    created += 1
                chosen.append(movie_id)
            con.execute("DELETE FROM recommendation_likes")
            con.executemany(
                "INSERT INTO recommendation_likes(movie_id,created_at) VALUES (?,?)",
                [(mid, utcnow()) for mid in chosen],
            )
            con.execute(
                "INSERT OR REPLACE INTO settings(key,value) VALUES ('recommendation_mode',?)",
                (mode,),
            )
            con.execute(
                "INSERT OR REPLACE INTO settings(key,value) VALUES ('recommendation_onboarding','complete')"
            )
            return created
