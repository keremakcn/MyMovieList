import json
import os
import sqlite3
import sys
import time

from datetime import datetime
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from flask import Flask, render_template, request, redirect, send_from_directory


# --- Paths: work both as a normal script and as a PyInstaller .exe ---
#
# BASE_DIR is where the *bundled, read-only* app files live (templates,
# static/style.css, static/script.js). When running from source this
# is just the folder app.py is in; when frozen into a PyInstaller
# --onefile .exe, it's a temporary extraction folder (sys._MEIPASS)
# that gets wiped after the program exits -- so nothing the user needs
# to keep (the database, downloaded posters) can live there.
#
# DATA_DIR is where the app *writes* things that must survive between
# runs: the SQLite database and downloaded poster images. From source
# this is also just the app folder (convenient for development); when
# frozen it's a MovieWatchlist folder under the user's AppData, which
# always exists and is always writable, no matter where the .exe was
# double-clicked from.

def _get_base_dir():
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def _get_data_dir():
    if getattr(sys, "frozen", False):
        root = os.environ.get("APPDATA") or os.path.expanduser("~")
        data_dir = os.path.join(root, "MovieWatchlist")
    else:
        data_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


BASE_DIR = _get_base_dir()
DATA_DIR = _get_data_dir()
DB_PATH = os.path.join(DATA_DIR, "movies.db")
POSTERS_DIR = os.path.join(DATA_DIR, "posters")


class SQL:
    """A tiny stand-in for the cs50 library's SQL class, covering just
    what this app uses: db.execute(query, *params). SELECT statements
    return a list of dict-like rows (row["column"] works); anything
    else just runs and commits. Swapped in instead of cs50 so the app
    has one less third-party dependency to fight with when packaging
    into a .exe (cs50 is meant for Harvard's CS50 course environment,
    not for distributing a standalone app)."""

    def __init__(self, path):
        self._path = path

    def execute(self, query, *params):
        con = sqlite3.connect(self._path)
        con.row_factory = sqlite3.Row
        try:
            cur = con.cursor()
            cur.execute(query, params)

            if query.strip().split(None, 1)[0].upper() in ("SELECT", "PRAGMA"):
                return [dict(row) for row in cur.fetchall()]

            con.commit()
            return cur.rowcount
        finally:
            con.close()


app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
)
# Never let the browser (or the desktop app's embedded WebView2)
# cache static/style.css and static/script.js. Without this, updating
# the app and rebuilding the .exe can still show old CSS/JS, because
# WebView2 keeps its own persistent cache between runs -- there's no
# "hard refresh" shortcut in a native window like there is in a
# regular browser tab.
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

db = SQL(DB_PATH)

# Base schema, for a completely fresh install (a brand-new DATA_DIR
# with no movies.db yet -- e.g. the first time someone runs the .exe).
db.execute("""
    CREATE TABLE IF NOT EXISTS movies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        year INTEGER,
        genre TEXT,
        status TEXT NOT NULL DEFAULT 'Watchlist',
        rating INTEGER,
        note TEXT,
        favorite INTEGER NOT NULL DEFAULT 0,
        watched_date TEXT,
        catalog_id INTEGER
    )
""")


def _ensure_column(table, column, coltype):
    """Add a column to an existing table if it isn't there yet, so
    upgrading from an older version of this app doesn't require
    manually editing the database. Just tries the ALTER TABLE and
    ignores the error if the column is already there."""
    try:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
    except Exception:
        pass


# `movies` caches everything needed to display a library entry
# (poster, overview, runtime, director, cast, TMDB score) locally, so
# it renders even with no internet connection -- only searching for
# new movies needs to reach TMDB.
_ensure_column("movies", "tmdb_id", "INTEGER")
_ensure_column("movies", "poster_path", "TEXT")
_ensure_column("movies", "overview", "TEXT")
_ensure_column("movies", "runtime", "INTEGER")
_ensure_column("movies", "director", "TEXT")
_ensure_column("movies", "cast_list", "TEXT")
_ensure_column("movies", "score_percent", "INTEGER")

# If a movie somehow got added twice for the same tmdb_id before (a
# double-click, or two quick form submits racing each other), clean
# it up now, keeping the oldest row -- otherwise creating the UNIQUE
# index right below would fail.
db.execute("""
    DELETE FROM movies
    WHERE tmdb_id IS NOT NULL
    AND id NOT IN (
        SELECT MIN(id) FROM movies
        WHERE tmdb_id IS NOT NULL
        GROUP BY tmdb_id
    )
""")

# The real fix: make it impossible at the database level for the same
# TMDB movie to be added twice, even if two "Add" requests race each
# other (SQLite treats each NULL as distinct, so manually-added
# movies -- which have no tmdb_id -- are unaffected).
try:
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_movies_tmdb_id ON movies(tmdb_id)")
except Exception:
    pass

# --- TMDB helpers -----------------------------------------------------
#
# A tmdb_id's poster/overview/cast almost never changes, so we cache
# responses in memory for a while instead of hitting the TMDB API on
# every single page load. This also lets the index page (which needs
# a poster for every movie in the list) fetch them in parallel instead
# of one HTTP request at a time.

_TMDB_CACHE_TTL_SECONDS = 6 * 60 * 60  # 6 hours
_tmdb_cache = {}
_tmdb_cache_lock = Lock()


# A tiny key-value table for app settings that need to persist
# permanently (right now: the TMDB token) -- not tied to a browser
# session/cookie, so it survives clearing cookies, private/incognito
# windows, or opening the app in a different browser.
db.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
""")


def get_setting(key, default=None):
    rows = db.execute("SELECT value FROM settings WHERE key = ?", key)
    return rows[0]["value"] if rows else default


def set_setting(key, value):
    if value is None:
        db.execute("DELETE FROM settings WHERE key = ?", key)
    else:
        db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            key,
            value
        )


def get_tmdb_token():
    """The token saved via /settings takes priority over the .env
    one. Stored in the database (not a session/cookie), so it's
    shared across every browser/window and survives cookies being
    cleared -- appropriate for this being a single-user app."""
    return get_setting("tmdb_token") or os.environ.get("TMDB_ACCESS_TOKEN")


def _fetch_tmdb_movie(tmdb_id, full, token):
    if not tmdb_id or not token:
        return None

    append = "&append_to_response=credits" if full else ""

    api_request = Request(
        f"https://api.themoviedb.org/3/movie/{tmdb_id}?language=en-US{append}",
        headers={"Authorization": f"Bearer {token}"}
    )

    try:
        with urlopen(api_request, timeout=5) as response:
            return json.load(response)
    except (HTTPError, URLError, TimeoutError):
        return None


def get_tmdb_data(tmdb_id, full=False, token=None):
    """Return TMDB info for a movie, cached in memory for a while.

    Always includes: poster_url, score_percent, title, year, genre.
    full=True additionally includes: overview, runtime, director, cast
    (used on movie detail pages and when adding a movie to the library).

    token: pass this explicitly if you already have it on hand (e.g.
    to avoid a redundant DB read); otherwise it's looked up via
    get_tmdb_token() automatically.
    """
    if not tmdb_id:
        return None

    if token is None:
        token = get_tmdb_token()

    # If nobody has a token saved right now, don't touch the cache at
    # all -- we don't want a "no token" miss to poison the cache for
    # later once a token is added.
    if not token:
        return None

    cache_key = (tmdb_id, full)
    now = time.time()

    with _tmdb_cache_lock:
        cached = _tmdb_cache.get(cache_key)
        if cached and now - cached["time"] < _TMDB_CACHE_TTL_SECONDS:
            return cached["data"]

    data = _fetch_tmdb_movie(tmdb_id, full, token)
    result = None

    if data is not None:
        poster_path = data.get("poster_path")
        poster_size = "w500" if full else "w342"
        vote_average = data.get("vote_average")
        release_date = data.get("release_date", "") or ""

        result = {
            "poster_url": (
                f"https://image.tmdb.org/t/p/{poster_size}{poster_path}"
                if poster_path
                else None
            ),
            # A 0-100 "score" like MyGameList/Metacritic, rounded from
            # TMDB's 0-10 vote_average. None if TMDB has no votes yet.
            "score_percent": (
                round(vote_average * 10)
                if vote_average
                else None
            ),
            "title": data.get("title"),
            "year": int(release_date[:4]) if release_date[:4].isdigit() else None,
            "genre": ", ".join(g["name"] for g in data.get("genres", [])) or None
        }

        if full:
            credits = data.get("credits", {})

            result["overview"] = data.get("overview")
            result["runtime"] = data.get("runtime")
            result["director"] = next(
                (
                    person["name"]
                    for person in credits.get("crew", [])
                    if person.get("job") == "Director"
                ),
                None
            )
            result["cast"] = [
                person["name"]
                for person in credits.get("cast", [])[:5]
            ]

    # Cache the result (including failures, briefly) so a slow/down
    # TMDB API doesn't get hammered on every request.
    with _tmdb_cache_lock:
        _tmdb_cache[cache_key] = {"data": result, "time": now}

    return result


def cache_poster_locally(tmdb_id, poster_url):
    """Download a TMDB poster once and save it under DATA_DIR/posters,
    so it (and everything else about a library movie) can still be
    displayed with no internet connection later. Returns a local URL
    like '/posters/603.jpg', or None if there's no poster or the
    download fails (in which case the app falls back to showing no
    poster, rather than failing to add the movie)."""
    if not poster_url:
        return None

    try:
        os.makedirs(POSTERS_DIR, exist_ok=True)
        filename = f"{tmdb_id}.jpg"
        local_path = os.path.join(POSTERS_DIR, filename)

        if not os.path.exists(local_path):
            with urlopen(poster_url, timeout=8) as response:
                image_bytes = response.read()
            with open(local_path, "wb") as f:
                f.write(image_bytes)

        return f"/posters/{filename}"
    except (HTTPError, URLError, TimeoutError, OSError):
        return None


_genre_map_cache = {"data": None, "time": 0}
_GENRE_MAP_TTL_SECONDS = 24 * 60 * 60  # TMDB's genre list barely changes


def get_tmdb_genre_map(token):
    """id -> name for TMDB's movie genres (e.g. 28 -> 'Action'). Only
    needed to label genres in *search results*, since /search/movie
    only returns genre_ids, not names."""
    now = time.time()

    if _genre_map_cache["data"] and now - _genre_map_cache["time"] < _GENRE_MAP_TTL_SECONDS:
        return _genre_map_cache["data"]

    mapping = {}

    if token:
        api_request = Request(
            "https://api.themoviedb.org/3/genre/movie/list?language=en-US",
            headers={"Authorization": f"Bearer {token}"}
        )
        try:
            with urlopen(api_request, timeout=5) as response:
                data = json.load(response)
            mapping = {g["id"]: g["name"] for g in data.get("genres", [])}
        except (HTTPError, URLError, TimeoutError):
            pass

    _genre_map_cache["data"] = mapping
    _genre_map_cache["time"] = now
    return mapping


@app.route("/posters/<path:filename>")
def poster_file(filename):
    """Serve downloaded posters from DATA_DIR/posters. These live
    outside the bundled static/ folder because, when packaged as a
    .exe, static/ is inside the read-only (and temporary) PyInstaller
    bundle -- posters need to be somewhere that persists between
    runs."""
    return send_from_directory(POSTERS_DIR, filename)


@app.route("/")
def index():
    status_filter = request.args.get("status", "all")
    sort = request.args.get("sort", "")

    # No more join to movie_catalog -- each library movie now carries
    # its own cached poster/score directly, so this reads entirely
    # from local data (works with no internet connection).
    query = "SELECT * FROM movies"
    params = []

    if status_filter == "Watchlist":
        query += " WHERE status = ?"
        params.append("Watchlist")
    elif status_filter == "Watched":
        query += " WHERE status = ?"
        params.append("Watched")
    elif status_filter == "favorite":
        query += " WHERE favorite = 1"
    # status_filter == "all" (or anything unrecognized): no WHERE clause

    sort_clauses = {
        "rating_desc": "rating DESC",
        "rating_asc": "rating ASC",
        "year_desc": "year DESC",
        "year_asc": "year ASC",
        # NULL watched_date (never watched) always sorts last here,
        # regardless of direction, so unwatched movies don't jumble
        # in with a "watched date" sort.
        "watched_desc": "(watched_date IS NULL), watched_date DESC",
        "watched_asc": "(watched_date IS NULL), watched_date ASC",
        # Same NULL-last treatment for manually-added movies with no
        # cached TMDB score.
        "tmdb_desc": "(score_percent IS NULL), score_percent DESC",
        "tmdb_asc": "(score_percent IS NULL), score_percent ASC",
        "added_desc": "id DESC",
        "added_asc": "id ASC",
    }

    if sort in sort_clauses:
        query += f" ORDER BY {sort_clauses[sort]}"
    else:
        sort = ""
        query += """
            ORDER BY
                CASE
                    WHEN favorite = 1 THEN 1
                    WHEN status = 'Watched' THEN 2
                    WHEN status = 'Watchlist' THEN 3
                    ELSE 4
                END,
                id DESC
        """

    movies = db.execute(query, *params)

    watchlist_movies = db.execute(
        "SELECT COUNT(*) AS total FROM movies WHERE status = ?",
        "Watchlist"
    )[0]["total"]

    watched_movies = db.execute(
        "SELECT COUNT(*) AS total FROM movies WHERE status = ?",
        "Watched"
    )[0]["total"]

    favorite_movies = db.execute(
        "SELECT COUNT(*) AS total FROM movies WHERE favorite = 1"
    )[0]["total"]

    average_rating = db.execute(
        "SELECT ROUND(AVG(rating), 1) AS average_rating FROM movies WHERE rating IS NOT NULL"
    )[0]["average_rating"]

    return render_template(
        "index.html",
        movies=movies,
        watchlist_movies=watchlist_movies,
        watched_movies=watched_movies,
        favorite_movies=favorite_movies,
        average_rating=average_rating,
        tmdb_token_missing=not bool(get_tmdb_token()),
        status_filter=status_filter,
        sort=sort,
        current_url=f"/?status={status_filter}&sort={sort}"
    )


@app.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        token = request.form.get("tmdb_token", "").strip()
        set_setting("tmdb_token", token or None)
        return redirect("/")

    return render_template(
        "settings.html",
        has_token=bool(get_tmdb_token()),
        has_saved_token=bool(get_setting("tmdb_token"))
    )


@app.route("/add", methods=["GET", "POST"])
def add():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        genre = request.form.get("genre", "").strip() or None
        status = request.form.get("status")
        note = request.form.get("note", "").strip() or None

        if not title:
            return render_template("add.html", error="Title is required.")

        if status not in ("Watchlist", "Watched"):
            status = "Watchlist"

        year_raw = request.form.get("year", "").strip()
        year = None
        if year_raw:
            try:
                year = int(year_raw)
            except ValueError:
                year = None

        rating_raw = request.form.get("rating", "").strip()
        rating = None
        if rating_raw:
            try:
                rating = int(rating_raw)
                if not 1 <= rating <= 10:
                    rating = None
            except ValueError:
                rating = None

        db.execute(
            """
            INSERT INTO movies
            (title, year, genre, status, rating, note)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            title,
            year,
            genre,
            status,
            rating,
            note,
        )

        return redirect("/")

    return render_template("add.html")


@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    results = []
    error = None

    if query:
        token = get_tmdb_token()

        if not token:
            error = "Add your TMDB token in Settings to search for movies."
        else:
            genre_map = get_tmdb_genre_map(token)

            api_request = Request(
                f"https://api.themoviedb.org/3/search/movie"
                f"?query={quote(query)}&language=en-US&include_adult=false",
                headers={"Authorization": f"Bearer {token}"}
            )

            try:
                with urlopen(api_request, timeout=8) as response:
                    data = json.load(response)

                for m in data.get("results", [])[:20]:
                    release_date = m.get("release_date", "") or ""
                    poster_path = m.get("poster_path")

                    results.append({
                        "tmdb_id": m["id"],
                        "title": m.get("title"),
                        "year": (
                            int(release_date[:4])
                            if release_date[:4].isdigit()
                            else None
                        ),
                        "genre": ", ".join(
                            genre_map[g]
                            for g in m.get("genre_ids", [])
                            if g in genre_map
                        ),
                        "poster_url": (
                            f"https://image.tmdb.org/t/p/w185{poster_path}"
                            if poster_path
                            else None
                        )
                    })
            except (HTTPError, URLError, TimeoutError):
                error = "Couldn't reach TMDB. Check your internet connection."

    return render_template(
        "search.html",
        results=results,
        query=query,
        error=error
    )
def _add_movie_from_catalog(status):
    """Add a movie (found via live TMDB search) to the library. Fetches
    full details from TMDB once, downloads the poster to disk, and
    stores everything in the `movies` row -- so this movie can be
    displayed later with no internet connection at all."""
    tmdb_id_raw = request.form.get("movie_id")

    try:
        tmdb_id = int(tmdb_id_raw)
    except (TypeError, ValueError):
        return redirect("/search")

    existing = db.execute(
        "SELECT id FROM movies WHERE tmdb_id = ?",
        tmdb_id
    )

    if existing:
        return redirect(f"/movie/{existing[0]['id']}")

    tmdb = get_tmdb_data(tmdb_id, full=True)

    if not tmdb:
        return redirect("/search")

    poster_path = cache_poster_locally(tmdb_id, tmdb.get("poster_url"))
    cast_list = ", ".join(tmdb.get("cast") or []) or None

    watched_date_clause = "DATE('now')" if status == "Watched" else "NULL"

    try:
        db.execute(
            f"""
            INSERT INTO movies
            (title, year, genre, status, watched_date, tmdb_id, poster_path,
             overview, runtime, director, cast_list, score_percent)
            VALUES (?, ?, ?, ?, {watched_date_clause}, ?, ?, ?, ?, ?, ?, ?)
            """,
            tmdb.get("title"),
            tmdb.get("year"),
            tmdb.get("genre"),
            status,
            tmdb_id,
            poster_path,
            tmdb.get("overview"),
            tmdb.get("runtime"),
            tmdb.get("director"),
            cast_list,
            tmdb.get("score_percent"),
        )
    except sqlite3.IntegrityError:
        # Someone else (or a double-click) added this same movie in
        # the moment between our check above and this INSERT. Rather
        # than crashing or creating a duplicate, just send them to
        # the copy that won the race.
        existing = db.execute(
            "SELECT id FROM movies WHERE tmdb_id = ?",
            tmdb_id
        )
        if existing:
            return redirect(f"/movie/{existing[0]['id']}")

    return redirect("/")


@app.route("/add_from_catalog", methods=["POST"])
def add_from_catalog():
    return _add_movie_from_catalog("Watchlist")


@app.route("/add_watched_from_catalog", methods=["POST"])
def add_watched_from_catalog():
    return _add_movie_from_catalog("Watched")


@app.route("/edit/<int:movie_id>", methods=["GET", "POST"])
def edit(movie_id):
    movies = db.execute(
        "SELECT * FROM movies WHERE id = ?",
        movie_id
    )

    if not movies:
        return redirect("/")

    movie = movies[0]

    # Remember where the person came from (the library, or this
    # movie's detail page) so Save/Cancel can send them back there
    # instead of always landing on the detail page.
    next_url = request.args.get("next", "")
    if not next_url.startswith("/") or next_url.startswith("//"):
        next_url = f"/movie/{movie_id}"

    if request.method == "POST":
        rating_raw = request.form.get("rating", "").strip()
        rating = None
        if rating_raw:
            try:
                rating = int(rating_raw)
                if not 1 <= rating <= 10:
                    return render_template(
                        "edit.html", movie=movie, next_url=next_url,
                        error="Rating must be between 1 and 10."
                    )
            except ValueError:
                return render_template(
                    "edit.html", movie=movie, next_url=next_url,
                    error="Rating must be a number."
                )

        note = request.form.get("note", "").strip() or None

        watched_date_raw = request.form.get("watched_date", "").strip()
        watched_date = None
        if watched_date_raw:
            try:
                datetime.strptime(watched_date_raw, "%Y-%m-%d")
                watched_date = watched_date_raw
            except ValueError:
                return render_template(
                    "edit.html", movie=movie, next_url=next_url,
                    error="Watched date must be a valid date."
                )

        db.execute(
            """
            UPDATE movies
            SET rating = ?, note = ?, watched_date = ?
            WHERE id = ?
            """,
            rating,
            note,
            watched_date,
            movie_id
        )

        return redirect(next_url)

    return render_template("edit.html", movie=movie, next_url=next_url)


def safe_next(default="/"):
    """Read a `next` value from the request (form field or query
    string) and use it as a redirect target, but only if it's a
    same-site path -- otherwise fall back to `default`. Used so
    actions triggered from the library (with filters/sort in the
    URL) or from a movie's detail page redirect back to wherever the
    person actually was, instead of always bouncing to a plain "/"."""
    next_url = request.values.get("next", "")
    if not next_url.startswith("/") or next_url.startswith("//"):
        return default
    return next_url


@app.route("/favorite/<int:movie_id>", methods=["POST"])
def favorite(movie_id):
    movies = db.execute(
        "SELECT favorite, status FROM movies WHERE id = ?",
        movie_id
    )

    if not movies:
        return redirect("/")

    movie = movies[0]
    new_value = 0 if movie["favorite"] else 1

    if new_value == 1:
        db.execute(
            """
            UPDATE movies
            SET favorite = 1,
                status = 'Watched',
                watched_date = DATE('now')
            WHERE id = ?
            """,
            movie_id
        )
    else:
        db.execute(
            "UPDATE movies SET favorite = 0 WHERE id = ?",
            movie_id
        )

    return redirect(safe_next())

@app.route("/status/<int:movie_id>", methods=["POST"])
def change_status(movie_id):
    movies = db.execute(
        "SELECT status FROM movies WHERE id = ?",
        movie_id
    )

    if not movies:
        return redirect("/")

    movie = movies[0]

    if movie["status"] == "Watchlist":
        db.execute(
            """
            UPDATE movies
            SET status = ?, watched_date = DATE('now')
            WHERE id = ?
            """,
            "Watched",
            movie_id
        )
    else:
        db.execute(
            """
            UPDATE movies
            SET status = ?, watched_date = NULL
            WHERE id = ?
            """,
            "Watchlist",
            movie_id
        )

    return redirect(safe_next())


@app.route("/delete/<int:movie_id>", methods=["POST"])
def delete(movie_id):
    db.execute(
        "DELETE FROM movies WHERE id = ?",
        movie_id
    )

    return redirect(safe_next())


@app.route("/movie/<int:movie_id>")
def movie(movie_id):
    movies = db.execute(
        "SELECT * FROM movies WHERE id = ?",
        movie_id
    )

    if not movies:
        return redirect("/")

    movie = movies[0]

    # Everything here comes from the movie's own cached columns --
    # no TMDB request, so this page works with no internet connection
    # for any movie that was added through search.
    tmdb = None
    if movie["poster_path"] or movie["overview"]:
        tmdb = {
            "poster_url": movie["poster_path"],
            "overview": movie["overview"],
            "runtime": movie["runtime"],
            "director": movie["director"],
            "cast": movie["cast_list"].split(", ") if movie["cast_list"] else [],
            "score_percent": movie["score_percent"],
        }

    return render_template("movie.html", movie=movie, tmdb=tmdb)
@app.route("/catalog_movie/<int:tmdb_id>")
def catalog_movie(tmdb_id):
    # This is a live preview of a movie found via search, *before*
    # it's added to the library -- so unlike movie(), this always
    # needs to reach TMDB and requires internet.
    tmdb = get_tmdb_data(tmdb_id, full=True)

    if not tmdb:
        return redirect("/search")

    movie = {
        "id": tmdb_id,
        "title": tmdb.get("title"),
        "year": tmdb.get("year"),
        "genre": tmdb.get("genre"),
    }

    existing = db.execute(
        "SELECT id, status, favorite FROM movies WHERE tmdb_id = ?",
        tmdb_id
    )

    return render_template(
        "catalog_movie.html",
        movie=movie,
        tmdb=tmdb,
        existing=existing
    )


# --- Launcher -----------------------------------------------------
#
# This block only runs when the script is executed directly
# (`python app.py`, or the packaged .exe double-clicked) -- not when
# imported by `flask run` or a WSGI server. It's what turns this into
# a self-contained desktop app: starts a real (non-dev) server and
# opens the browser to it automatically, so there's no URL to type
# and no separate "flask run" step to remember.
if __name__ == "__main__":
    import threading
    import webbrowser

    HOST = "127.0.0.1"
    PORT = 5000

    def _open_browser():
        webbrowser.open(f"http://{HOST}:{PORT}")

    # Small delay so the browser doesn't try to connect before the
    # server has actually started listening.
    threading.Timer(1.0, _open_browser).start()

    try:
        from waitress import serve
        print(f"Movie Watchlist is running at http://{HOST}:{PORT}")
        print("Close this window to stop the app.")
        serve(app, host=HOST, port=PORT)
    except ImportError:
        # Waitress isn't installed (e.g. running from source without
        # having run `pip install waitress` yet) -- fall back to
        # Flask's built-in server so `python app.py` still works.
        print("waitress not installed -- using Flask's built-in server.")
        print("Run 'pip install waitress' for a more robust server.")
        app.run(host=HOST, port=PORT)