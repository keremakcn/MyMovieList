"""Secure Letterboxd (ZIP/CSV) and IMDb (CSV) external library importer."""

import csv
import io
import math
import re
import zipfile
from datetime import date

from storage import search_fold
from tmdb_client import TMDBError, movie_summary

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_ZIP_UNCOMPRESSED_BYTES = 25 * 1024 * 1024
MAX_ZIP_FILES = 50
MAX_IMPORT_ITEMS = 10_000
MAX_NOTE_LENGTH = 20_000
MAX_TITLE_LENGTH = 300
MAX_GENRE_LENGTH = 300
ZIP_CHUNK_BYTES = 65_536

LETTERBOXD_FILES = (
    ("watched.csv", "watched"),
    ("ratings.csv", "ratings"),
    ("diary.csv", "diary"),
    ("reviews.csv", "reviews"),
    ("watchlist.csv", "watchlist"),
)
LETTERBOXD_FILE_MAP = dict(LETTERBOXD_FILES)
LETTERBOXD_FILM_URI_KINDS = frozenset(("watched", "ratings", "watchlist"))
LETTERBOXD_IGNORED_DIRS = frozenset(
    ("deleted", "orphaned", "likes", "lists", "comments", "__macosx")
)

IMDB_FILM_TYPES = frozenset(("", "movie", "tvmovie", "short", "video"))


def normalize_title(value):
    """Case- and diacritic-insensitive title key for deduplication."""
    folded = search_fold(value or "")
    return re.sub(r"\s+", " ", folded).strip()


def title_slug(value):
    """Punctuation-insensitive folded title for resilient catalog matching."""
    folded = search_fold(value or "")
    return re.sub(r"[^a-z0-9]+", " ", folded).strip()


def clean_title(value):
    text = re.sub(r"[\r\n\t]+", " ", str(value or "")).strip()
    return text[:MAX_TITLE_LENGTH].strip()


def clean_genre(value):
    text = re.sub(r"[\r\n\t]+", " ", str(value or "")).strip()
    if not text:
        return None
    return text[:MAX_GENRE_LENGTH].strip() or None


def clean_note(value):
    if value is None:
        return None
    text = str(value).replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return None
    return text[:MAX_NOTE_LENGTH]


def parse_year(value):
    text = str(value or "").strip()
    if not text:
        return None
    match = re.match(r"^(\d{4})(?:\D|$)", text)
    if not match:
        return None
    year = int(match.group(1))
    return year if 1800 <= year <= 2200 else None


def parse_iso_date(value):
    text = str(value or "").strip()
    if not text:
        return None
    candidate = text[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", candidate):
        return None
    try:
        date.fromisoformat(candidate)
    except ValueError:
        return None
    return candidate


def convert_letterboxd_rating(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        stars = float(text)
    except ValueError:
        return None
    if not math.isfinite(stars) or stars <= 0:
        return None
    return max(1, min(10, int(round(stars * 2))))


def parse_imdb_rating(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        score = float(text)
    except ValueError:
        return None
    if not math.isfinite(score) or score < 1 or score > 10:
        return None
    return max(1, min(10, int(round(score))))


def normalize_uri(value):
    text = str(value or "").strip().rstrip("/")
    return text.lower() if text else ""


def _decode_csv_bytes(raw):
    if not raw:
        raise ValueError("The uploaded file is empty.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ValueError("Choose a file under 25 MB.")
    if b"\x00" in raw:
        raise ValueError("The CSV file is malformed and could not be read.")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("The CSV file could not be decoded as UTF-8.") from error


def _read_csv_rows(text):
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""))
        fieldnames = reader.fieldnames
        if not fieldnames:
            raise ValueError("The CSV file has no header row.")
        headers = [str(name or "").strip().lower() for name in fieldnames]
        if not any(headers):
            raise ValueError("The CSV file has no header row.")
        rows = []
        for raw_row in reader:
            row = {}
            for key, value in raw_row.items():
                if not isinstance(key, str):
                    continue
                normalized_key = key.strip().lower()
                if normalized_key:
                    row[normalized_key] = "" if value is None else str(value)
            rows.append(row)
        return set(headers) - {""}, rows
    except csv.Error as error:
        raise ValueError("The CSV file is malformed and could not be read.") from error


def _is_letterboxd_headers(headers):
    return "name" in headers and bool(
        headers & {"letterboxd uri", "year", "watched date", "review", "rating", "date"}
    )


def _is_imdb_headers(headers):
    return "title" in headers and bool(
        headers
        & {"const", "your rating", "title type", "imdb rating", "date rated", "position"}
    )


def _detect_letterboxd_csv_kind(headers, filename=""):
    if "review" in headers:
        return "reviews"
    if "watched date" in headers or "rewatch" in headers:
        return "diary"
    if "rating" in headers:
        return "ratings"
    base = str(filename or "").replace("\\", "/").rsplit("/", 1)[-1].lower()
    if "watchlist" in base:
        return "watchlist"
    return "watched"


def _merge_letterboxd_tables(tables):
    """Merge Letterboxd CSV rows into unified film entries."""
    entries = []
    uri_index = {}
    title_year_index = {}

    def _find_entry(norm_title, year, uri, kind):
        if uri and uri in uri_index:
            return uri_index[uri]
        ty_key = (norm_title, year)
        existing = title_year_index.get(ty_key)
        if existing is not None:
            # In real Letterboxd exports, diary/reviews carry entry URIs rather
            # than film URIs. Only treat two rows with the same (title, year) as
            # distinct films when both provide different film-level URIs.
            if (
                kind in LETTERBOXD_FILM_URI_KINDS
                and existing["_film_uri"]
                and uri
                and existing["_film_uri"] != uri
            ):
                return None
            return existing
        return None

    for kind, rows in tables:
        for row in rows:
            title = clean_title(row.get("name", ""))
            if not title:
                continue
            year = parse_year(row.get("year"))
            norm_title = normalize_title(title)
            if not norm_title:
                continue
            uri = normalize_uri(row.get("letterboxd uri"))

            entry = _find_entry(norm_title, year, uri, kind)
            if entry is None:
                if len(entries) >= MAX_IMPORT_ITEMS:
                    raise ValueError("An import can contain up to 10,000 films.")
                entry = {
                    "title": title,
                    "year": year,
                    "status": "Watchlist" if kind == "watchlist" else "Watched",
                    "rating": None,
                    "watched_date": None,
                    "note": None,
                    "genre": None,
                    "external_id": uri or None,
                    "_film_uri": uri if kind in LETTERBOXD_FILM_URI_KINDS else "",
                    "_rating_from_ratings": False,
                    "_rating_date": "",
                    "_watched_date_priority": 0,
                    "_notes": [],
                }
                entries.append(entry)
                title_year_index.setdefault((norm_title, year), entry)
                if uri:
                    uri_index[uri] = entry
            else:
                if uri:
                    uri_index.setdefault(uri, entry)
                    if kind in LETTERBOXD_FILM_URI_KINDS and not entry["_film_uri"]:
                        entry["_film_uri"] = uri
                    if not entry["external_id"]:
                        entry["external_id"] = uri

            if kind != "watchlist":
                entry["status"] = "Watched"

            row_date = (
                parse_iso_date(row.get("watched date"))
                or parse_iso_date(row.get("date"))
                or ""
            )
            rating = convert_letterboxd_rating(row.get("rating"))
            if rating is not None:
                if kind == "ratings":
                    entry["rating"] = rating
                    entry["_rating_from_ratings"] = True
                elif not entry["_rating_from_ratings"] and (
                    entry["rating"] is None or row_date >= entry["_rating_date"]
                ):
                    entry["rating"] = rating
                    entry["_rating_date"] = row_date

            if kind in ("diary", "reviews"):
                explicit_watched = parse_iso_date(row.get("watched date"))
                fallback_date = parse_iso_date(row.get("date"))
                if explicit_watched:
                    if (
                        entry["_watched_date_priority"] < 3
                        or not entry["watched_date"]
                        or explicit_watched > entry["watched_date"]
                    ):
                        entry["watched_date"] = explicit_watched
                        entry["_watched_date_priority"] = 3
                elif fallback_date and entry["_watched_date_priority"] <= 2:
                    if (
                        entry["_watched_date_priority"] < 2
                        or not entry["watched_date"]
                        or fallback_date > entry["watched_date"]
                    ):
                        entry["watched_date"] = fallback_date
                        entry["_watched_date_priority"] = 2
            elif kind in ("watched", "ratings"):
                fallback_date = parse_iso_date(row.get("date"))
                if fallback_date and entry["_watched_date_priority"] <= 1:
                    if (
                        entry["_watched_date_priority"] < 1
                        or not entry["watched_date"]
                        or fallback_date > entry["watched_date"]
                    ):
                        entry["watched_date"] = fallback_date
                        entry["_watched_date_priority"] = 1

            if kind == "reviews":
                review = clean_note(row.get("review"))
                if review and review not in entry["_notes"]:
                    entry["_notes"].append(review)

    result = []
    for entry in entries:
        note = clean_note("\n\n".join(entry["_notes"])) if entry["_notes"] else None
        status = entry["status"]
        watched_date = entry["watched_date"] if status == "Watched" else None
        result.append(
            {
                "title": entry["title"],
                "year": entry["year"],
                "status": status,
                "rating": entry["rating"],
                "watched_date": watched_date,
                "note": note,
                "genre": None,
                "external_id": entry["external_id"],
            }
        )
    return {"source": "letterboxd", "items": result, "skipped_non_films": 0}


def parse_letterboxd_csv(raw, filename="", kind=None):
    """Parse a single Letterboxd CSV export file."""
    text = _decode_csv_bytes(raw)
    headers, rows = _read_csv_rows(text)
    if not _is_letterboxd_headers(headers):
        raise ValueError(
            "This CSV does not match a Letterboxd export format."
        )
    detected_kind = kind or _detect_letterboxd_csv_kind(headers, filename)
    if detected_kind not in LETTERBOXD_FILE_MAP.values():
        raise ValueError("Unsupported Letterboxd CSV type.")
    return _merge_letterboxd_tables([(detected_kind, rows)])


def _validate_zip_member_path(info):
    name = info.filename or ""
    if (
        not name
        or "\x00" in name
        or name.startswith(("/", "\\"))
        or "\\" in name
        or ":" in name
    ):
        raise ValueError("Archive contains unsafe file paths.")
    parts = [part for part in name.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise ValueError("Archive contains unsafe file paths.")
    # Reject Unix symlinks stored in ZIP external attributes.
    if ((info.external_attr >> 16) & 0o170000) == 0o120000:
        raise ValueError("Archive contains unsafe file paths.")
    return parts


def parse_letterboxd_zip(raw):
    """Safely inspect and merge supported CSVs from a Letterboxd ZIP archive."""
    if not raw:
        raise ValueError("The uploaded file is empty.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ValueError("Choose a file under 25 MB.")
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError) as error:
        raise ValueError("Choose a valid Letterboxd ZIP archive.") from error

    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_ZIP_FILES:
            raise ValueError("Archive contains too many files.")

        declared_total = 0
        selected = {}
        for info in infos:
            parts = _validate_zip_member_path(info)
            if info.file_size < 0 or info.file_size > MAX_ZIP_UNCOMPRESSED_BYTES:
                raise ValueError("Archive exceeds the 25 MB uncompressed size limit.")
            declared_total += info.file_size
            if declared_total > MAX_ZIP_UNCOMPRESSED_BYTES:
                raise ValueError("Archive exceeds the 25 MB uncompressed size limit.")
            if info.is_dir() or not parts:
                continue
            lower_parts = [part.lower() for part in parts]
            if any(parent in LETTERBOXD_IGNORED_DIRS for parent in lower_parts[:-1]):
                continue
            # Accept root-level CSVs or CSVs nested inside a single export folder.
            if len(parts) > 2:
                continue
            basename = lower_parts[-1]
            if basename in LETTERBOXD_FILE_MAP:
                existing = selected.get(basename)
                if existing is None or len(parts) < existing[0]:
                    selected[basename] = (len(parts), info)

        if not selected:
            raise ValueError(
                "No supported Letterboxd CSV files were found in this archive."
            )

        actual_total = 0
        tables = []
        for csv_name, kind in LETTERBOXD_FILES:
            picked = selected.get(csv_name)
            if picked is None:
                continue
            info = picked[1]
            chunks = []
            try:
                with zf.open(info, "r") as stream:
                    while True:
                        chunk = stream.read(ZIP_CHUNK_BYTES)
                        if not chunk:
                            break
                        actual_total += len(chunk)
                        if actual_total > MAX_ZIP_UNCOMPRESSED_BYTES:
                            raise ValueError(
                                "Archive exceeds the 25 MB uncompressed size limit."
                            )
                        chunks.append(chunk)
            except (zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError, OSError) as error:
                raise ValueError("Choose a valid Letterboxd ZIP archive.") from error
            member_bytes = b"".join(chunks)
            if not member_bytes.strip():
                continue
            text = _decode_csv_bytes(member_bytes)
            headers, rows = _read_csv_rows(text)
            if not _is_letterboxd_headers(headers):
                raise ValueError(
                    "The CSV file inside the archive does not match a Letterboxd export."
                )
            tables.append((kind, rows))

        if not tables:
            raise ValueError(
                "No supported Letterboxd CSV files were found in this archive."
            )

    return _merge_letterboxd_tables(tables)


def parse_imdb_csv(raw, filename=""):
    """Parse an IMDb ratings or watchlist CSV export, skipping non-film rows."""
    text = _decode_csv_bytes(raw)
    headers, rows = _read_csv_rows(text)
    if not _is_imdb_headers(headers):
        raise ValueError("This CSV does not match an IMDb export format.")

    base = str(filename or "").replace("\\", "/").rsplit("/", 1)[-1].lower()
    is_watched_list = any(
        token in base for token in ("watched", "ratings", "checkins", "check-ins")
    )

    items = []
    by_const = {}
    by_title_year = {}
    skipped_non_films = 0

    for row in rows:
        raw_type = row.get("title type", "")
        normalized_type = re.sub(r"[\s_-]+", "", raw_type.strip().lower())
        if normalized_type not in IMDB_FILM_TYPES:
            skipped_non_films += 1
            continue

        title = clean_title(row.get("title", ""))
        if not title:
            continue
        norm_title = normalize_title(title)
        if not norm_title:
            continue

        year = parse_year(row.get("year")) or parse_year(row.get("release date"))
        const = str(row.get("const", "")).strip().lower()
        rating = parse_imdb_rating(row.get("your rating"))
        watched_date = parse_iso_date(row.get("date rated"))
        genre = clean_genre(row.get("genres"))
        status = (
            "Watched"
            if (rating is not None or watched_date is not None or is_watched_list)
            else "Watchlist"
        )
        if status != "Watched":
            watched_date = None

        existing = (
            by_const.get(const) if const else None
        ) or by_title_year.get((norm_title, year))
        if existing is not None:
            if status == "Watched":
                existing["status"] = "Watched"
            if rating is not None:
                existing["rating"] = rating
            if watched_date and (
                not existing["watched_date"] or watched_date > existing["watched_date"]
            ):
                existing["watched_date"] = watched_date
            if genre and not existing["genre"]:
                existing["genre"] = genre
            continue

        if len(items) >= MAX_IMPORT_ITEMS:
            raise ValueError("An import can contain up to 10,000 films.")

        entry = {
            "title": title,
            "year": year,
            "status": status,
            "rating": rating,
            "watched_date": watched_date,
            "note": None,
            "genre": genre,
            "external_id": const or None,
        }
        items.append(entry)
        if const:
            by_const[const] = entry
        by_title_year[(norm_title, year)] = entry

    return {
        "source": "imdb",
        "items": items,
        "skipped_non_films": skipped_non_films,
    }


def parse_external_upload(raw, filename="", source="auto"):
    """Detect and parse an uploaded Letterboxd (ZIP/CSV) or IMDb (CSV) export."""
    if not raw:
        raise ValueError("The uploaded file is empty.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ValueError("Choose a file under 25 MB.")

    name = str(filename or "").strip()
    lower_name = name.lower()
    ext = ""
    if "." in lower_name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]:
        ext = "." + lower_name.rsplit(".", 1)[-1]
    if ext and ext not in (".zip", ".csv"):
        raise ValueError("Choose a Letterboxd (.zip or .csv) or IMDb (.csv) file.")

    is_zip = ext == ".zip" or raw[:4] in (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
    if is_zip:
        if source == "imdb":
            raise ValueError("IMDb exports must be uploaded as a CSV file.")
        return parse_letterboxd_zip(raw)

    if source == "letterboxd":
        return parse_letterboxd_csv(raw, filename=name)
    if source == "imdb":
        return parse_imdb_csv(raw, filename=name)

    text = _decode_csv_bytes(raw)
    headers, _ = _read_csv_rows(text)
    if _is_imdb_headers(headers):
        return parse_imdb_csv(raw, filename=name)
    if _is_letterboxd_headers(headers):
        return parse_letterboxd_csv(raw, filename=name)
    raise ValueError(
        "Unsupported or malformed CSV file. Upload a Letterboxd (ZIP/CSV) or IMDb (CSV) export."
    )


def _normalize_candidate(item):
    if not isinstance(item, dict):
        return None
    if type(item.get("tmdb_id")) is int and 1 <= item["tmdb_id"] <= 9_999_999_999:
        return {
            "tmdb_id": item["tmdb_id"],
            "title": clean_title(item.get("title") or ""),
            "original_title": clean_title(item.get("original_title") or ""),
            "year": parse_year(item.get("year")),
            "poster_url": item.get("poster_url"),
            "overview": item.get("overview") or "",
            "score_percent": item.get("score_percent"),
        }
    if type(item.get("id")) is int and 1 <= item["id"] <= 9_999_999_999:
        summary = movie_summary(item)
        summary["title"] = clean_title(summary.get("title") or "")
        summary["original_title"] = clean_title(summary.get("original_title") or "")
        return summary
    return None


def pick_best_tmdb_match(candidates, title, year):
    """Select the best matching TMDB film candidate by title and exact/close year."""
    target_slug = title_slug(title)
    if not target_slug:
        return None

    best_rank = None
    best_candidate = None
    for index, raw_candidate in enumerate(candidates or ()):
        candidate = _normalize_candidate(raw_candidate)
        if candidate is None:
            continue
        cand_slugs = [
            slug
            for slug in (
                title_slug(candidate.get("title")),
                title_slug(candidate.get("original_title")),
            )
            if slug
        ]
        if not cand_slugs:
            continue

        exact_title = target_slug in cand_slugs
        partial_title = False
        if not exact_title:
            for slug in cand_slugs:
                if target_slug in slug or slug in target_slug:
                    shorter, longer = sorted((len(target_slug), len(slug)))
                    if longer > 0 and shorter / longer >= 0.6:
                        partial_title = True
                        break

        cand_year = candidate.get("year")
        if year is not None and cand_year is not None:
            year_diff = abs(cand_year - year)
            if exact_title and year_diff <= 2:
                year_tier = year_diff
            elif partial_title and year_diff == 0:
                year_tier = 0
            else:
                continue
        elif exact_title:
            year_tier = 3
        else:
            continue

        title_tier = 0 if exact_title else 1
        rank = (year_tier, title_tier, index)
        if best_rank is None or rank < best_rank:
            best_rank = rank
            best_candidate = candidate

    return best_candidate


def _search_tmdb(tmdb, title):
    if hasattr(tmdb, "search_movies"):
        return tmdb.search_movies(title)
    data = tmdb.get(
        "search/movie",
        query=title,
        language="en-US",
        include_adult="false",
        page=1,
    )
    return data.get("results", []) if isinstance(data, dict) else []


def import_external_library(parsed, db, tmdb=None, *, skipped_non_films=0):
    """Import parsed Letterboxd/IMDb items into db without overwriting existing films."""
    if isinstance(parsed, dict):
        items = list(parsed.get("items") or [])
        non_films = int(parsed.get("skipped_non_films") or 0) + int(
            skipped_non_films or 0
        )
    else:
        items = list(parsed or [])
        non_films = int(skipped_non_films or 0)

    if len(items) > MAX_IMPORT_ITEMS:
        raise ValueError("An import can contain up to 10,000 films.")

    existing_rows = db.query(
        "SELECT id, tmdb_id, title, year FROM movies WHERE deleted_at IS NULL"
    )
    existing_tmdb_ids = {
        row["tmdb_id"] for row in existing_rows if row.get("tmdb_id")
    }
    existing_title_years = {
        (normalize_title(row["title"]), row["year"])
        for row in existing_rows
        if row.get("title")
    }

    imported = 0
    matched_tmdb = 0
    added_custom = 0
    skipped_existing = 0

    tmdb_available = tmdb is not None
    consecutive_errors = 0

    for item in items:
        title = clean_title(item.get("title", ""))
        if not title:
            continue
        year = parse_year(item.get("year"))
        norm_title = normalize_title(title)
        if not norm_title:
            continue

        if (norm_title, year) in existing_title_years:
            skipped_existing += 1
            continue

        status = item.get("status") if item.get("status") in ("Watched", "Watchlist") else "Watchlist"
        rating = item.get("rating")
        if type(rating) is not int or not 1 <= rating <= 10:
            rating = None
        watched_date = (
            parse_iso_date(item.get("watched_date")) if status == "Watched" else None
        )
        note = clean_note(item.get("note"))
        genre = clean_genre(item.get("genre"))

        match = None
        if tmdb_available:
            try:
                candidates = _search_tmdb(tmdb, title)
                consecutive_errors = 0
                match = pick_best_tmdb_match(candidates, title, year)
            except TMDBError as error:
                consecutive_errors += 1
                if error.status == 429 or consecutive_errors >= 3:
                    tmdb_available = False
            except (OSError, TimeoutError, ValueError, TypeError):
                consecutive_errors += 1
                if consecutive_errors >= 3:
                    tmdb_available = False

        if match is not None:
            tmdb_id = match["tmdb_id"]
            match_title = clean_title(match.get("title") or title) or title
            match_year = match.get("year") if match.get("year") is not None else year
            match_norm_title = normalize_title(match_title)
            if (
                tmdb_id in existing_tmdb_ids
                or (match_norm_title, match_year) in existing_title_years
            ):
                skipped_existing += 1
                continue
            values = {
                "tmdb_id": tmdb_id,
                "title": match_title,
                "year": match_year,
                "genre": genre,
                "poster_path": match.get("poster_url"),
                "overview": match.get("overview") or None,
                "score_percent": match.get("score_percent"),
                "status": status,
                "rating": rating,
                "note": note,
                "watched_date": watched_date,
                "favorite": 0,
            }
            _, created = db.add_tmdb(values)
            existing_tmdb_ids.add(tmdb_id)
            existing_title_years.add((norm_title, year))
            existing_title_years.add((match_norm_title, match_year))
            if created:
                imported += 1
                matched_tmdb += 1
            else:
                skipped_existing += 1
        else:
            values = {
                "title": title,
                "year": year,
                "genre": genre,
                "status": status,
                "rating": rating,
                "note": note,
                "watched_date": watched_date,
                "favorite": 0,
            }
            db.add_custom(values)
            existing_title_years.add((norm_title, year))
            imported += 1
            added_custom += 1

    return {
        "imported": imported,
        "matched_tmdb": matched_tmdb,
        "added_custom": added_custom,
        "skipped_existing": skipped_existing,
        "skipped_non_films": non_films,
    }
