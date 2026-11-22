"""Tests for Letterboxd (ZIP/CSV) and IMDb (CSV) external library importer."""

import io
import zipfile
from pathlib import Path

import pytest
from test_app import post

import external_import as ext
from personal_data import from_movie
from storage import Database
from tmdb_client import TMDBError


def make_zip(files, *, compression=zipfile.ZIP_DEFLATED):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=compression) as zf:
        for name, content in files.items():
            if isinstance(content, tuple):
                info, payload = content
                zf.writestr(info, payload)
            else:
                zf.writestr(name, content)
    return buf.getvalue()


def csrf_token(client):
    client.get("/settings")
    with client.session_transaction() as sess:
        return sess["csrf_token"]


def test_letterboxd_full_zip_merge_bom_ratings_and_watchlist():
    long_review = "A" * 20_500
    payload = make_zip(
        {
            "watched.csv": (
                "\ufeffDate,Name,Year,Letterboxd URI\n"
                "2022-01-05,The Matrix,1999,https://boxd.it/2a1m\n"
                "2023-03-10,Past Lives,2023,https://boxd.it/past\n"
                "2023-04-01,Low Rated Film,2020,https://boxd.it/low\n"
            ).encode("utf-8"),
            "ratings.csv": (
                "\ufeffDate,Name,Year,Letterboxd URI,Rating\n"
                "2022-01-05,The Matrix,1999,https://boxd.it/2a1m,4.5\n"
                "2023-03-10,Past Lives,2023,https://boxd.it/past,3.5\n"
                "2023-04-01,Low Rated Film,2020,https://boxd.it/low,0.5\n"
            ).encode("utf-8"),
            "diary.csv": (
                "Date,Name,Year,Letterboxd URI,Rating,Rewatch,Tags,Watched Date\n"
                "2022-01-06,The Matrix,1999,https://boxd.it/entry-matrix,4.0,,sci-fi,2022-01-02\n"
                "2024-06-15,The Matrix,1999,https://boxd.it/entry-matrix-2,5.0,Yes,sci-fi,2024-06-14\n"
            ).encode("utf-8"),
            "reviews.csv": (
                "Date,Name,Year,Letterboxd URI,Rating,Rewatch,Review,Tags,Watched Date\n"
                f'2024-06-15,The Matrix,1999,https://boxd.it/rev-matrix,4.5,Yes,"{long_review}",,2024-06-14\n'
            ).encode("utf-8"),
            "watchlist.csv": (
                "Date,Name,Year,Letterboxd URI\n"
                "2024-01-01,The Matrix,1999,https://boxd.it/2a1m\n"
                "2024-02-02,Dune: Part Two,2024,https://boxd.it/dune2\n"
            ).encode("utf-8"),
            # Letterboxd exports include deleted/ and orphaned/ folders that must be ignored.
            "deleted/watched.csv": (
                "Date,Name,Year,Letterboxd URI\n"
                "2020-01-01,Deleted Film,2019,https://boxd.it/deleted\n"
            ).encode("utf-8"),
            "orphaned/reviews.csv": (
                "Date,Name,Year,Letterboxd URI,Rating,Rewatch,Review,Tags,Watched Date\n"
                "2020-01-01,Orphaned Film,2019,https://boxd.it/orphan,5.0,,nope,,2020-01-01\n"
            ).encode("utf-8"),
        }
    )

    parsed = ext.parse_letterboxd_zip(payload)
    assert parsed["source"] == "letterboxd"
    assert parsed["skipped_non_films"] == 0
    by_title = {item["title"]: item for item in parsed["items"]}
    assert set(by_title) == {"The Matrix", "Past Lives", "Low Rated Film", "Dune: Part Two"}

    matrix = by_title["The Matrix"]
    assert matrix["year"] == 1999
    assert matrix["status"] == "Watched"
    assert matrix["rating"] == 9  # 4.5 * 2 from ratings.csv
    assert matrix["watched_date"] == "2024-06-14"  # latest diary/review Watched Date
    assert len(matrix["note"]) == 20_000
    assert matrix["note"] == "A" * 20_000

    assert by_title["Past Lives"]["rating"] == 7  # 3.5 * 2
    assert by_title["Past Lives"]["watched_date"] == "2023-03-10"
    assert by_title["Low Rated Film"]["rating"] == 1  # 0.5 * 2

    dune = by_title["Dune: Part Two"]
    assert dune["status"] == "Watchlist"
    assert dune["rating"] is None
    assert dune["watched_date"] is None
    assert dune["note"] is None


def test_letterboxd_zip_supports_single_wrapper_folder_and_empty_member():
    payload = make_zip(
        {
            "letterboxd-alice-2026/watched.csv": (
                "Date,Name,Year,Letterboxd URI\n"
                "2025-05-01,In the Mood for Love,2000,https://boxd.it/mood\n"
            ).encode("utf-8"),
            "letterboxd-alice-2026/reviews.csv": b"",
        }
    )
    parsed = ext.parse_letterboxd_zip(payload)
    assert len(parsed["items"]) == 1
    assert parsed["items"][0]["title"] == "In the Mood for Love"
    assert parsed["items"][0]["status"] == "Watched"


def test_letterboxd_single_csv_imports():
    ratings_csv = (
        "\ufeffDate,Name,Year,Letterboxd URI,Rating\n"
        "2024-03-01,Parasite,2019,https://boxd.it/para,5.0\n"
        "2024-03-02,Arrival,2016,https://boxd.it/arr,2.5\n"
    ).encode("utf-8")
    parsed_ratings = ext.parse_external_upload(ratings_csv, "ratings.csv")
    assert parsed_ratings["source"] == "letterboxd"
    assert [(i["title"], i["status"], i["rating"]) for i in parsed_ratings["items"]] == [
        ("Parasite", "Watched", 10),
        ("Arrival", "Watched", 5),
    ]

    watchlist_csv = (
        "Date,Name,Year,Letterboxd URI\n"
        "2024-03-05,Stalker,1979,https://boxd.it/stalker\n"
    ).encode("utf-8")
    parsed_wl = ext.parse_external_upload(watchlist_csv, "watchlist.csv")
    assert parsed_wl["items"][0]["status"] == "Watchlist"
    assert parsed_wl["items"][0]["watched_date"] is None


def test_imdb_csv_import_movies_ratings_dates_watchlist_and_non_film_skip():
    imdb_ratings = (
        "\ufeffConst,Your Rating,Date Rated,Title,URL,Title Type,IMDb Rating,Runtime (mins),Year,Genres,Num Votes,Release Date,Directors\n"
        'tt0133093,9,2024-01-20,The Matrix,https://www.imdb.com/title/tt0133093/,movie,8.7,136,1999,"Action, Sci-Fi",2000000,1999-03-31,Lana Wachowski\n'
        'tt0903747,10,2024-01-21,Breaking Bad,https://www.imdb.com/title/tt0903747/,tvSeries,9.5,49,2008,"Crime, Drama",2100000,2008-01-20,\n'
        'tt2301451,10,2024-01-22,Ozymandias,https://www.imdb.com/title/tt2301451/,tvEpisode,10.0,48,2013,"Crime, Drama",210000,2013-09-15,Rian Johnson\n'
        'tt7366338,9,2024-01-23,Chernobyl,https://www.imdb.com/title/tt7366338/,tvMiniSeries,9.3,330,2019,"Drama, History",850000,2019-05-06,\n'
        'tt2140553,8,2024-01-24,The Last of Us,https://www.imdb.com/title/tt2140553/,videoGame,9.7,,2013,"Action, Adventure",70000,2013-06-14,\n'
        'tt0100001,8,2024-02-01,TV Film Example,https://www.imdb.com/title/tt0100001/,tvMovie,7.1,95,2005,Drama,1200,2005-04-01,\n'
        'tt0100002,,not-a-date,Unrated Short,https://www.imdb.com/title/tt0100002/,short,7.4,12,2021,Animation,500,2021-01-01,\n'
    ).encode("utf-8")

    parsed = ext.parse_external_upload(imdb_ratings, "my_imdb_export.csv")
    assert parsed["source"] == "imdb"
    assert parsed["skipped_non_films"] == 4
    by_title = {item["title"]: item for item in parsed["items"]}
    assert set(by_title) == {"The Matrix", "TV Film Example", "Unrated Short"}

    assert by_title["The Matrix"]["status"] == "Watched"
    assert by_title["The Matrix"]["rating"] == 9
    assert by_title["The Matrix"]["watched_date"] == "2024-01-20"
    assert by_title["The Matrix"]["genre"] == "Action, Sci-Fi"

    assert by_title["TV Film Example"]["status"] == "Watched"
    assert by_title["TV Film Example"]["rating"] == 8

    assert by_title["Unrated Short"]["status"] == "Watchlist"
    assert by_title["Unrated Short"]["rating"] is None
    assert by_title["Unrated Short"]["watched_date"] is None


def test_imdb_watchlist_csv_imports_unrated_as_watchlist():
    imdb_watchlist = (
        "Position,Const,Created,Modified,Description,Title,URL,Title Type,IMDb Rating,Runtime (mins),Year,Genres,Num Votes,Release Date,Directors\n"
        '1,tt0110912,2024-05-01,2024-05-01,,Pulp Fiction,https://www.imdb.com/title/tt0110912/,Movie,8.9,154,1994,"Crime, Drama",2200000,1994-10-14,Quentin Tarantino\n'
        '2,tt0944947,2024-05-01,2024-05-01,,Game of Thrones,https://www.imdb.com/title/tt0944947/,TV Series,9.2,57,2011,"Action, Drama",2300000,2011-04-17,\n'
    ).encode("utf-8")
    parsed = ext.parse_external_upload(imdb_watchlist, "imdb_watchlist.csv")
    assert parsed["source"] == "imdb"
    assert parsed["skipped_non_films"] == 1
    assert len(parsed["items"]) == 1
    assert parsed["items"][0]["title"] == "Pulp Fiction"
    assert parsed["items"][0]["status"] == "Watchlist"
    assert parsed["items"][0]["rating"] is None


def test_zip_bomb_and_oversized_archive_rejected(monkeypatch):
    # Highly compressible 26 MB zero/text payload compresses to < 50 KB -> classic zip bomb.
    bomb_bytes = ("Date,Name,Year,Letterboxd URI\n" + ("2024-01-01,A,2024,x\n" * 1_400_000)).encode(
        "utf-8"
    )
    assert len(bomb_bytes) > ext.MAX_ZIP_UNCOMPRESSED_BYTES
    bomb_zip = make_zip({"watched.csv": bomb_bytes}, compression=zipfile.ZIP_DEFLATED)
    assert len(bomb_zip) < 200_000

    with pytest.raises(ValueError, match="25 MB uncompressed"):
        ext.parse_letterboxd_zip(bomb_zip)

    # Even if compressed upload itself exceeds MAX_UPLOAD_BYTES.
    monkeypatch.setattr(ext, "MAX_UPLOAD_BYTES", 1024)
    with pytest.raises(ValueError, match="under 25 MB"):
        ext.parse_external_upload(b"a" * 2048, "watched.csv")


def test_zip_too_many_files_rejected():
    files = {
        f"file_{i}.txt": b"x" for i in range(ext.MAX_ZIP_FILES + 1)
    }
    files["watched.csv"] = b"Date,Name,Year,Letterboxd URI\n2024-01-01,A,2024,u\n"
    payload = make_zip(files)
    with pytest.raises(ValueError, match="too many files"):
        ext.parse_letterboxd_zip(payload)


@pytest.mark.parametrize(
    "bad_path",
    [
        "../watched.csv",
        "sub/../../watched.csv",
        "/etc/passwd",
        "C:/watched.csv",
    ],
)
def test_zip_path_traversal_rejected(bad_path):
    info = zipfile.ZipInfo("placeholder")
    info.filename = bad_path
    payload = make_zip(
        {bad_path: (info, b"Date,Name,Year,Letterboxd URI\n2024-01-01,A,2024,u\n")}
    )
    with pytest.raises(ValueError, match="unsafe file paths"):
        ext.parse_letterboxd_zip(payload)


def test_zip_literal_backslash_path_rejected():
    from types import SimpleNamespace

    # Raw ZIP bytes with backslash traversal (on Windows zipfile normalizes \ -> /,
    # on POSIX \ stays literal; both paths must be rejected).
    base = make_zip(
        {"../watched.csv": b"Date,Name,Year,Letterboxd URI\n2024-01-01,A,2024,u\n"}
    )
    crafted = base.replace(b"../watched.csv", b"..\\watched.csv")
    with pytest.raises(ValueError, match="unsafe file paths"):
        ext.parse_letterboxd_zip(crafted)

    # Also verify direct member-path validator rejects literal backslashes and NULs.
    for bad in ("folder\\watched.csv", "\\windows\\win.ini", "watched.csv\x00.txt"):
        with pytest.raises(ValueError, match="unsafe file paths"):
            ext._validate_zip_member_path(SimpleNamespace(filename=bad, external_attr=0))


def test_zip_symlink_entry_rejected():
    info = zipfile.ZipInfo("watched.csv")
    info.external_attr = (0o120777 << 16)
    payload = make_zip({"watched.csv": (info, b"/etc/passwd")})
    with pytest.raises(ValueError, match="unsafe file paths"):
        ext.parse_letterboxd_zip(payload)


@pytest.mark.parametrize(
    "raw,filename",
    [
        (b"", "watched.csv"),
        (b"\x00\x01\x02binary", "watched.csv"),
        (b"\xff\xfeinvalid-utf8", "watched.csv"),
        (b"col_a,col_b\n1,2\n", "unknown.csv"),
        (b"not a zip at all", "export.zip"),
        (b"hello", "notes.exe"),
    ],
)
def test_malformed_uploads_rejected(raw, filename):
    with pytest.raises(ValueError):
        ext.parse_external_upload(raw, filename)


def test_import_tmdb_match_offline_fallback_duplicate_preservation_and_sync_state(tmp_path):
    db = Database(tmp_path / "sync.db", owner_id="user-1")
    db.migrate()

    # Existing catalog film + existing custom film with user notes/ratings that must never be overwritten.
    existing_tmdb_id, _ = db.add_tmdb(
        {
            "tmdb_id": 603,
            "title": "The Matrix",
            "year": 1999,
            "status": "Watched",
            "rating": 10,
            "note": "Keep my original Matrix note!",
            "favorite": 1,
        }
    )
    existing_custom_id = db.add_custom(
        {
            "title": "Local Indie Film",
            "year": 2018,
            "status": "Watched",
            "rating": 7,
            "note": "Keep my custom note!",
            "favorite": 0,
        }
    )
    before_matrix = db.movie(existing_tmdb_id)
    before_custom = db.movie(existing_custom_id)

    class FakeTMDB:
        def search_movies(self, title):
            if title == "Dune":
                return [
                    {
                        "tmdb_id": 841,
                        "title": "Dune",
                        "original_title": "Dune",
                        "year": 1984,
                        "poster_url": "https://image.tmdb.org/t/p/w342/dune1984.jpg",
                        "overview": "1984 adaptation.",
                        "score_percent": 62,
                    },
                    {
                        "tmdb_id": 438631,
                        "title": "Dune",
                        "original_title": "Dune",
                        "year": 2021,
                        "poster_url": "https://image.tmdb.org/t/p/w342/dune2021.jpg",
                        "overview": "2021 adaptation.",
                        "score_percent": 78,
                    },
                ]
            if title == "The Matrix":
                return [
                    {
                        "tmdb_id": 603,
                        "title": "The Matrix",
                        "original_title": "The Matrix",
                        "year": 1999,
                        "poster_url": None,
                        "overview": "Simulated reality.",
                        "score_percent": 82,
                    }
                ]
            if title == "Rate Limited Film":
                raise TMDBError("Busy", status=429)
            return []

    parsed = {
        "source": "letterboxd",
        "items": [
            # Duplicate by (title, year)
            {
                "title": "The Matrix",
                "year": 1999,
                "status": "Watched",
                "rating": 2,
                "watched_date": "2020-01-01",
                "note": "Should NOT overwrite!",
                "genre": None,
            },
            # Duplicate custom film by (title, year)
            {
                "title": "local indie film",
                "year": 2018,
                "status": "Watchlist",
                "rating": 1,
                "watched_date": None,
                "note": "Should NOT overwrite custom!",
                "genre": None,
            },
            # Duplicate by TMDB ID even with different year (1998 vs 1999 -> close match to 603)
            {
                "title": "The Matrix",
                "year": 1998,
                "status": "Watched",
                "rating": 4,
                "watched_date": "2020-01-01",
                "note": "Also should NOT overwrite!",
                "genre": None,
            },
            # Should match Dune (2021, tmdb_id=438631), NOT Dune (1984)
            {
                "title": "Dune",
                "year": 2021,
                "status": "Watched",
                "rating": 9,
                "watched_date": "2021-10-25",
                "note": "Stunning sound design.",
                "genre": None,
            },
            # Triggers TMDB 429 -> must fall back cleanly to custom film without losing data
            {
                "title": "Rate Limited Film",
                "year": 2022,
                "status": "Watched",
                "rating": 8,
                "watched_date": "2023-05-05",
                "note": "Saved even while rate-limited.",
                "genre": "Drama",
            },
            # After 429 circuit-break, also falls back cleanly to custom film
            {
                "title": "Offline Followup",
                "year": 2023,
                "status": "Watchlist",
                "rating": None,
                "watched_date": None,
                "note": None,
                "genre": "Thriller",
            },
        ],
        "skipped_non_films": 2,
    }

    # Also test TMDB ID deduplication when title differs slightly via search_movies
    summary = ext.import_external_library(parsed, db, FakeTMDB())
    assert summary == {
        "imported": 3,
        "matched_tmdb": 1,
        "added_custom": 2,
        "skipped_existing": 3,
        "skipped_non_films": 2,
    }

    # Existing films are 100% untouched.
    assert db.movie(existing_tmdb_id) == before_matrix
    assert db.movie(existing_custom_id) == before_custom

    # Matched Dune 2021 has TMDB ID 438631 and personal fields intact.
    dune_rows = db.query("SELECT * FROM movies WHERE tmdb_id=438631")
    assert len(dune_rows) == 1
    dune = dune_rows[0]
    assert (dune["title"], dune["year"], dune["status"], dune["rating"], dune["watched_date"], dune["note"]) == (
        "Dune",
        2021,
        "Watched",
        9,
        "2021-10-25",
        "Stunning sound design.",
    )
    assert dune["record_key"] == "tmdb:438631"
    assert dune["order_key"]

    # Custom fallback films preserved rating, date, note, genre and have valid sync records.
    rl_rows = db.query("SELECT * FROM movies WHERE title='Rate Limited Film'")
    assert len(rl_rows) == 1
    rl = rl_rows[0]
    assert rl["tmdb_id"] is None
    assert rl["record_key"].startswith("custom:")
    assert (rl["rating"], rl["watched_date"], rl["note"], rl["genre"]) == (
        8,
        "2023-05-05",
        "Saved even while rate-limited.",
        "Drama",
    )

    # Every movie passes personal_data.from_movie validation and is queued in sync_dirty + sync_field_state.
    all_movies = db.query("SELECT * FROM movies")
    dirty_keys = {r["record_key"] for r in db.query("SELECT record_key FROM sync_dirty")}
    state_keys = {r["record_key"] for r in db.query("SELECT record_key FROM sync_field_state")}
    for row in all_movies:
        validated = from_movie(row)
        assert validated["status"] in ("Watched", "Watchlist")
        assert row["record_key"] in dirty_keys
        assert row["record_key"] in state_keys


def test_flask_route_csrf_and_end_to_end_letterboxd_and_imdb_uploads(app, client):
    # Missing CSRF token is rejected with 400.
    unauthenticated = client.post(
        "/settings/import-external",
        data={
            "import_file": (
                io.BytesIO(b"Date,Name,Year,Letterboxd URI\n2024-01-01,Test,2024,u\n"),
                "watched.csv",
            )
        },
        content_type="multipart/form-data",
    )
    assert unauthenticated.status_code == 400

    # Mock TMDB search_movies on the app's tmdb client.
    def fake_search(title, **kwargs):
        if title == "The Matrix":
            return [
                {
                    "tmdb_id": 603,
                    "title": "The Matrix",
                    "original_title": "The Matrix",
                    "year": 1999,
                    "poster_url": None,
                    "overview": "Simulated reality.",
                    "score_percent": 82,
                }
            ]
        return []

    app.extensions["tmdb"].search_movies = fake_search

    # Settings page renders the bilingual card.
    settings_html = client.get("/settings").get_data(as_text=True)
    assert "Import from Letterboxd or IMDb" in settings_html
    assert 'action="/settings/import-external"' in settings_html

    # End-to-end Letterboxd ZIP upload.
    token = csrf_token(client)
    zip_data = make_zip(
        {
            "watched.csv": b"Date,Name,Year,Letterboxd URI\n2024-01-01,The Matrix,1999,https://boxd.it/m\n",
            "ratings.csv": b"Date,Name,Year,Letterboxd URI,Rating\n2024-01-01,The Matrix,1999,https://boxd.it/m,4.5\n",
            "watchlist.csv": b"Date,Name,Year,Letterboxd URI\n2024-02-01,Obscure Custom,2022,https://boxd.it/c\n",
        }
    )
    response = client.post(
        "/settings/import-external",
        data={
            "csrf_token": token,
            "source": "auto",
            "import_file": (io.BytesIO(zip_data), "letterboxd-export.zip"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.location.endswith("/settings#external-import")

    redirected = client.get("/settings").get_data(as_text=True)
    assert "2 films imported (1 matched on TMDB, 1 custom). 0 existing kept." in redirected

    db = app.extensions["db"]
    rows = {r["title"]: r for r in db.query("SELECT * FROM movies WHERE deleted_at IS NULL")}
    assert rows["The Matrix"]["tmdb_id"] == 603
    assert rows["The Matrix"]["rating"] == 9
    assert rows["Obscure Custom"]["tmdb_id"] is None
    assert rows["Obscure Custom"]["status"] == "Watchlist"

    # End-to-end IMDb CSV upload in Turkish locale (with TV episode skipped + existing Matrix kept).
    post(client, "/settings/language", language="tr")
    tr_settings = client.get("/settings").get_data(as_text=True)
    assert "Letterboxd veya IMDb&#39;den içe aktar" in tr_settings or "Letterboxd veya IMDb'den içe aktar" in tr_settings

    token = csrf_token(client)
    imdb_csv = (
        "Const,Your Rating,Date Rated,Title,Title Type,Year,Genres\n"
        "tt0133093,5,2024-01-01,The Matrix,movie,1999,Sci-Fi\n"
        "tt0068646,10,2024-03-10,The Godfather,movie,1972,Crime\n"
        "tt0903747,10,2024-03-11,Breaking Bad,tvSeries,2008,Drama\n"
    ).encode("utf-8")
    response = client.post(
        "/settings/import-external",
        data={
            "csrf_token": token,
            "source": "imdb",
            "import_file": (io.BytesIO(imdb_csv), "ratings.csv"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert response.status_code == 303
    tr_flash = client.get("/settings").get_data(as_text=True)
    assert "1 film içe aktarıldı" in tr_flash
    assert "1 mevcut kayıt korundu" in tr_flash
    assert "1 film dışı kayıt atlandı" in tr_flash

    # Original Matrix rating from Letterboxd (9) was NOT overwritten by IMDb's rating (5).
    matrix_after = db.query("SELECT * FROM movies WHERE tmdb_id=603")[0]
    assert matrix_after["rating"] == 9

    # Malformed upload returns 422 with localized Turkish error.
    token = csrf_token(client)
    bad = client.post(
        "/settings/import-external",
        data={
            "csrf_token": token,
            "source": "auto",
            "import_file": (io.BytesIO(b"foo,bar\n1,2\n"), "bad.csv"),
        },
        content_type="multipart/form-data",
    )
    assert bad.status_code == 422
    assert "Desteklenmeyen veya bozuk CSV dosyası" in bad.get_data(as_text=True)


def test_packaging_allowlists_include_external_import():
    root = Path(__file__).resolve().parents[1]
    gradle = (root / "android/app/build.gradle").read_text(encoding="utf-8")
    assert "'external_import.py'" in gradle
    verify_macos = (root / "scripts/verify_macos.py").read_text(encoding="utf-8")
    assert '"external_import"' in verify_macos


def test_tmdb_client_search_movies_helper():
    from tmdb_client import TMDBClient

    client = TMDBClient()
    captured = {}

    def fake_get(path, **params):
        captured["path"] = path
        captured["params"] = params
        return {
            "results": [
                {
                    "id": 603,
                    "title": "The Matrix",
                    "original_title": "The Matrix",
                    "release_date": "1999-03-31",
                    "poster_path": "/matrix.jpg",
                    "overview": "Simulated reality.",
                    "vote_average": 8.2,
                    "vote_count": 1000,
                }
            ]
        }

    client.get = fake_get
    results = client.search_movies("The Matrix")
    assert captured["path"] == "search/movie"
    assert captured["params"]["query"] == "The Matrix"
    assert captured["params"]["include_adult"] == "false"
    assert len(results) == 1
    assert results[0]["tmdb_id"] == 603
    assert results[0]["year"] == 1999

