"""Local persistence. Migrations never discard library records."""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from unicodedata import combining, normalize
from uuid import uuid4


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def search_fold(value):
    """Case/diacritic-insensitive search; never used to write movie names or IDs."""
    normalized = normalize("NFKD", (value or "").casefold().replace("ı", "i"))
    return "".join(character for character in normalized if not combining(character))


class Database:
    def __init__(self, path, owner_id=None):
        self.path = str(path)
        self.owner_id = owner_id

    def changed(self, con, movie_id):
        from sync_store import track_movie

        track_movie(con, movie_id, queue=bool(self.owner_id))

    @contextmanager
    def connect(self, write=False):
        con = sqlite3.connect(self.path, timeout=15)
        con.row_factory = sqlite3.Row
        con.create_function("search_fold", 1, search_fold, deterministic=True)
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

    def library_stats(self):
        """One local summary for the selected library, excluding removed films."""
        return self.query(
            "SELECT COUNT(*) total, "
            "COALESCE(SUM(status='Watchlist'),0) watchlist, "
            "COALESCE(SUM(status='Watched'),0) watched, "
            "COALESCE(SUM(favorite=1),0) favorites, "
            "ROUND(AVG(rating),1) average "
            "FROM movies WHERE deleted_at IS NULL"
        )[0]

    def profile_films(self):
        """Small local shelves; personal notes never enter the profile view."""
        fields = "id,title,year,tmdb_id,poster_path,rating,watched_date,catalog_pending"
        favorites = self.query(
            f"SELECT {fields} FROM movies WHERE deleted_at IS NULL AND favorite=1 "
            "ORDER BY order_key DESC,id DESC LIMIT 6"
        )
        recent = self.query(
            f"SELECT {fields} FROM movies WHERE deleted_at IS NULL AND status='Watched' "
            "AND date(watched_date) IS NOT NULL "
            "ORDER BY watched_date DESC,order_key DESC,id DESC LIMIT 6"
        )
        dated = bool(recent)
        if not dated:
            recent = self.query(
                f"SELECT {fields} FROM movies WHERE deleted_at IS NULL "
                "ORDER BY order_key DESC,id DESC LIMIT 6"
            )
        return {"favorites": favorites, "recent": recent, "dated": dated}

    def showcase_films(self, keys):
        """Resolve only the owner's explicit picks, in their chosen order."""
        if not keys:
            return []
        rows = self.query(
            "SELECT id,record_key,title,year,tmdb_id,poster_path,rating,catalog_pending "
            "FROM movies WHERE deleted_at IS NULL AND record_key IN ("
            + ",".join("?" for _ in keys)
            + ")",
            *keys,
        )
        by_key = {movie["record_key"]: movie for movie in rows}
        return [by_key[key] for key in keys if key in by_key]

    def showcase_choices(self, query, page):
        """Paged local library search; no notes or online catalog requests."""
        clauses, params = ["deleted_at IS NULL"], []
        if query:
            clauses.append("""(search_fold(title) LIKE search_fold(?) ESCAPE '\\' OR EXISTS (
                SELECT 1 FROM movie_metadata c WHERE c.tmdb_id=movies.tmdb_id AND (
                search_fold(c.english_title) LIKE search_fold(?) ESCAPE '\\' OR
                search_fold(c.original_title) LIKE search_fold(?) ESCAPE '\\' OR
                search_fold(c.turkish_title) LIKE search_fold(?) ESCAPE '\\')))""")
            pattern = (
                "%"
                + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                + "%"
            )
            params.extend([pattern] * 4)
        where = " AND ".join(clauses)
        count = self.query("SELECT COUNT(*) n FROM movies WHERE " + where, *params)[0][
            "n"
        ]
        pages = max(1, (count + 19) // 20)
        page = max(1, min(page, pages))
        rows = self.query(
            "SELECT id,record_key,title,year,tmdb_id,poster_path,catalog_pending FROM movies WHERE "
            + where
            + " ORDER BY order_key DESC,id DESC LIMIT 20 OFFSET ?",
            *params,
            (page - 1) * 20,
        )
        return {"movies": rows, "page": page, "pages": pages, "count": count}

    def migrate(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with self.connect() as con:
            version = con.execute("PRAGMA user_version").fetchone()[0]
            if version > 4:
                raise RuntimeError("This library was created by a newer app version.")
            has_movies = con.execute(
                "SELECT 1 FROM sqlite_master WHERE name='movies'"
            ).fetchone()
            if has_movies and version < 4:
                backup_path = (
                    self.path
                    + ".before-v4-"
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
                "year": "INTEGER",
                "genre": "TEXT",
                "status": "TEXT NOT NULL DEFAULT 'Watchlist'",
                "rating": "INTEGER",
                "note": "TEXT",
                "favorite": "INTEGER NOT NULL DEFAULT 0",
                "watched_date": "TEXT",
                "catalog_id": "INTEGER",
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
                "record_key": "TEXT",
                "order_key": "TEXT",
                "sync_added_at": "TEXT",
                "catalog_pending": "INTEGER NOT NULL DEFAULT 0",
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
            # Discovery credentials now live exclusively in the hosted gateway.
            con.execute("PRAGMA secure_delete=ON")
            con.execute("DELETE FROM settings WHERE key='tmdb_token'")
            con.execute("""CREATE TABLE IF NOT EXISTS recommendation_likes (
                movie_id INTEGER PRIMARY KEY REFERENCES movies(id), created_at TEXT NOT NULL)""")
            con.execute("""CREATE TABLE IF NOT EXISTS recommendation_dismissals (
                tmdb_id INTEGER PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL)""")
            con.execute("""CREATE TABLE IF NOT EXISTS movie_metadata (
                tmdb_id INTEGER PRIMARY KEY CHECK(tmdb_id>0), english_title TEXT NOT NULL,
                original_title TEXT NOT NULL, turkish_title TEXT NOT NULL,
                data_json TEXT NOT NULL, fetched_at TEXT NOT NULL)""")
            # Legacy IDs determine existing order, including removed films.
            # A portable key preserves that order on another device.
            for row in con.execute(
                "SELECT id,tmdb_id,created_at FROM movies WHERE record_key IS NULL ORDER BY id"
            ).fetchall():
                suffix = str(uuid4())
                key = f"tmdb:{row['tmdb_id']}" if row["tmdb_id"] else f"custom:{suffix}"
                con.execute(
                    "UPDATE movies SET record_key=?,order_key=?,sync_added_at=? WHERE id=?",
                    (
                        key,
                        f"{row['id']:020}:{suffix}",
                        row["created_at"] or utcnow(),
                        row["id"],
                    ),
                )
            con.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_movies_record_key ON movies(record_key)"
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_movies_active_order ON movies(deleted_at,order_key)"
            )
            from sync_store import create_tables

            create_tables(con)
            con.execute("PRAGMA user_version=4")

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
                    self.changed(con, existing["id"])
                return existing["id"], False
            values = dict(values, created_at=utcnow(), updated_at=utcnow())
            columns = ",".join(values)
            cur = con.execute(
                f"INSERT INTO movies ({columns}) VALUES ({','.join('?' for _ in values)})",
                tuple(values.values()),
            )
            movie_id = cur.lastrowid
            self.changed(con, movie_id)
            return movie_id, True

    def add_custom(self, values):
        values = dict(values, created_at=utcnow(), updated_at=utcnow())
        with self.connect(write=True) as con:
            cur = con.execute(
                "INSERT INTO movies ("
                + ",".join(values)
                + ") VALUES ("
                + ",".join("?" for _ in values)
                + ")",
                tuple(values.values()),
            )
            movie_id = cur.lastrowid
            self.changed(con, movie_id)
            return movie_id

    def update_personal(self, movie_id, values):
        if not set(values) <= {"note", "rating", "watched_date", "favorite", "status"}:
            raise ValueError("Unsupported personal fields.")
        values = dict(values, updated_at=utcnow())
        with self.connect(write=True) as con:
            changed = con.execute(
                "UPDATE movies SET "
                + ",".join(k + "=?" for k in values)
                + " WHERE id=? AND deleted_at IS NULL",
                (*values.values(), movie_id),
            ).rowcount
            if changed:
                self.changed(con, movie_id)
            return changed

    def remove(self, movie_id):
        with self.connect(write=True) as con:
            row = con.execute("SELECT * FROM movies WHERE id=?", (movie_id,)).fetchone()
            if not row:
                return None
            marker = row["deleted_at"] or utcnow()
            con.execute("UPDATE movies SET deleted_at=? WHERE id=?", (marker, movie_id))
            if row["deleted_at"] is None:
                self.changed(con, movie_id)
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
            self.changed(con, movie_id)
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
                self.changed(con, movie_id)
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
