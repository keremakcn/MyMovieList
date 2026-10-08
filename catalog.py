"""Verified film metadata, persistent bilingual content and safe library presentation.

English library columns remain canonical. Language affects copied display values,
never movie identity or personal fields. Credits and translations share one request.
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from storage import utcnow
from tmdb_client import TMDBError, movie_details


def text(value):
    return value.strip() if isinstance(value, str) else ""


def translated_content(raw):
    """Prefer the Turkish/Turkey translation, with field-by-field fallback."""
    translations = raw.get("translations") or {}
    items = translations.get("translations", [])
    candidates = [
        item
        for item in items
        if isinstance(item, dict) and item.get("iso_639_1") == "tr"
    ]
    candidates.sort(key=lambda item: item.get("iso_3166_1") != "TR")
    result = {"title": "", "overview": ""}
    for item in candidates:
        data = item.get("data")
        if isinstance(data, dict):
            for field in result:
                if not result[field]:
                    result[field] = text(data.get(field))
    return result


def display_summary(movie, locale):
    result = dict(movie)
    # Keep English-original titles familiar, and use Turkish-original names in TR.
    if locale == "tr" and movie.get("original_language") in ("tr", "en"):
        result["title"] = text(movie.get("original_title")) or movie["title"]
    return result


class CatalogService:
    def __init__(self, db, tmdb, *, background=True):
        self.db, self.tmdb = db, tmdb
        self.locks = [Lock() for _ in range(32)]
        self.background = background
        self.executor = None
        self.state_lock = Lock()
        self.pending = set()
        self.retry_at = {}
        self.failures = {}

    def cached(self, ids):
        ids = list(dict.fromkeys(mid for mid in ids if type(mid) is int and mid > 0))
        if not ids:
            return {}
        records = self.db.query(
            "SELECT tmdb_id,data_json FROM movie_metadata WHERE tmdb_id IN ("
            + ",".join("?" for _ in ids)
            + ")",
            *ids,
        )
        found = {}
        for record in records:
            try:
                payload = json.loads(record["data_json"])
                details = payload["details"]
                if (
                    type(details["tmdb_id"]) is int
                    and details["tmdb_id"] == record["tmdb_id"]
                    and isinstance(details["title"], str)
                    and isinstance(details["entities"], dict)
                    and isinstance(details["overview"], str)
                    and isinstance(payload["tr"], dict)
                ):
                    found[record["tmdb_id"]] = payload
            except (ValueError, KeyError, TypeError):
                # A damaged metadata cache must never make the personal library fail.
                continue
        return found

    def details(self, tmdb_id, *, force=False, features=False):
        if type(tmdb_id) is not int or not 1 <= tmdb_id <= 9_999_999_999:
            raise TMDBError("The movie could not be verified. Please try again.", 502)
        with self.locks[tmdb_id % len(self.locks)]:
            cached = self.cached([tmdb_id]).get(tmdb_id)
            if (
                cached
                and not force
                and (
                    not features
                    or cached["details"].get("recommendation_features_version") == 1
                )
            ):
                return cached["details"]
            if not force and self.retry_at.get(tmdb_id, 0) > time.monotonic():
                message, status = self.failures[tmdb_id]
                raise TMDBError(
                    message, status, self.retry_at[tmdb_id] - time.monotonic()
                )
            if force:
                self.tmdb.invalidate(f"movie/{tmdb_id}")
            try:
                raw = self.tmdb.get(
                    f"movie/{tmdb_id}",
                    language="en-US",
                    append_to_response="credits,keywords,translations",
                )
                if (
                    not isinstance(raw, dict)
                    or type(raw.get("id")) is not int
                    or raw["id"] != tmdb_id
                ):
                    raise TMDBError(
                        "The movie could not be verified. Please try again.", 502
                    )
                credits = raw.get("credits")
                translations = raw.get("translations", {})
                if (
                    not isinstance(credits, dict)
                    or not isinstance(credits.get("cast"), list)
                    or not isinstance(credits.get("crew"), list)
                    or not isinstance(translations, dict)
                    or not isinstance(translations.get("translations", []), list)
                    or (
                        "id" in translations
                        and (
                            type(translations["id"]) is not int
                            or translations["id"] != tmdb_id
                        )
                    )
                ):
                    raise TMDBError(
                        "Movie discovery returned an unexpected response. Please try again.",
                        502,
                    )
                groups = [
                    credits["cast"],
                    credits["crew"],
                    raw.get("production_companies", []),
                ]
                keywords = raw.get("keywords")
                collection = raw.get("belongs_to_collection")
                if (
                    keywords is not None
                    and (
                        not isinstance(keywords, dict)
                        or (
                            "id" in keywords
                            and (
                                type(keywords["id"]) is not int
                                or keywords["id"] != tmdb_id
                            )
                        )
                        or not isinstance(keywords.get("keywords"), list)
                        or any(
                            not isinstance(k, dict)
                            or type(k.get("id")) is not int
                            or k["id"] < 1
                            for k in keywords.get("keywords", [])
                        )
                    )
                    or collection is not None
                    and (
                        not isinstance(collection, dict)
                        or type(collection.get("id")) is not int
                        or collection["id"] < 1
                    )
                ):
                    raise TMDBError(
                        "Movie discovery returned an unexpected response. Please try again.",
                        502,
                    )
                if (
                    any(not isinstance(group, list) for group in groups)
                    or any(
                        not isinstance(item, dict)
                        or type(item.get("id")) is not int
                        or item["id"] < 1
                        or not isinstance(item.get("name"), str)
                        for group in groups
                        for item in group
                    )
                    or not isinstance(raw.get("title"), str)
                    or not isinstance(raw.get("overview") or "", str)
                ):
                    raise TMDBError(
                        "Movie discovery returned an unexpected response. Please try again.",
                        502,
                    )
                details = movie_details(raw)
                payload = {"details": details, "tr": translated_content(raw)}
                original_title = text(raw.get("original_title"))
                turkish_title = (
                    original_title
                    if raw.get("original_language") == "tr"
                    else payload["tr"]["title"]
                )
                self.db.execute(
                    """INSERT INTO movie_metadata(tmdb_id,english_title,original_title,turkish_title,data_json,fetched_at)
                    VALUES(?,?,?,?,?,?) ON CONFLICT(tmdb_id) DO UPDATE SET
                    english_title=excluded.english_title,original_title=excluded.original_title,
                    turkish_title=excluded.turkish_title,data_json=excluded.data_json,fetched_at=excluded.fetched_at""",
                    tmdb_id,
                    details["title"],
                    original_title,
                    turkish_title,
                    json.dumps(payload, ensure_ascii=False),
                    utcnow(),
                )
                self.retry_at.pop(tmdb_id, None)
                self.failures.pop(tmdb_id, None)
                return details
            except TMDBError as error:
                self.failures[tmdb_id] = (str(error), error.status)
                self.retry_at[tmdb_id] = time.monotonic() + min(
                    60, max(3, error.retry_after or 3)
                )
                raise

    def present(self, movies, locale, *, fetch=False):
        movies = list(movies)
        cached = self.cached([m.get("tmdb_id") for m in movies])
        if fetch:
            missing = [
                m["tmdb_id"]
                for m in movies
                if m.get("tmdb_id") and m["tmdb_id"] not in cached
            ]

            def prepare(mid):
                try:
                    self.details(mid)
                except TMDBError:
                    pass  # Display English content when Turkish isn't available offline.

            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(prepare, dict.fromkeys(missing)))
            cached = self.cached([m.get("tmdb_id") for m in movies])
        results = []
        for movie in movies:
            result = display_summary(movie, locale)
            payload = cached.get(movie.get("tmdb_id"))
            aliases = [movie.get("title", ""), movie.get("original_title", "")]
            if payload:
                canonical = payload["details"]
                if movie.get("catalog_pending"):
                    result["title"] = canonical["title"]
                aliases.extend(
                    [
                        canonical["title"],
                        canonical.get("original_title", ""),
                        payload["tr"].get("title", ""),
                    ]
                )
                if locale == "tr":
                    if canonical.get("original_language") == "tr":
                        result["title"] = (
                            text(canonical.get("original_title"))
                            or text(payload["tr"].get("title"))
                            or movie["title"]
                        )
                    result["overview"] = (
                        text(payload["tr"].get("overview"))
                        or canonical["overview"]
                        or movie.get("overview", "")
                    )
            result["search_title"] = " ".join(
                dict.fromkeys(alias for alias in aliases if alias)
            )
            results.append(result)
        return results

    def library_detail(self, row, locale):
        """Older entries hydrate automatically; offline reads still use saved data."""
        verified = None
        if row.get("tmdb_id"):
            try:
                verified = self.details(row["tmdb_id"])
                self.fill_missing(row["tmdb_id"], verified)
                row = self.db.movie(row["id"]) or row
            except TMDBError:
                pass
        display = self.present([row], locale)[0]
        try:
            entities = json.loads(row.get("entities_json") or "{}")
            if not isinstance(entities, dict):
                entities = {}
        except (ValueError, TypeError):
            entities = {}
        if verified is not None:
            # Older movie rows may contain only a truncated cast. The verified,
            # persistent cache supplies the complete credits without rewriting notes.
            entities = verified["entities"]
        details = dict(
            display,
            poster_url=row.get("poster_path"),
            cast=(row.get("cast_list") or "").split(", "),
            entities=entities,
        )
        return display, details

    def fill_missing(self, tmdb_id, details):
        # Metadata-only backfill: never rewrites titles, dates, order or personal data.
        with self.db.connect(write=True) as con:
            row = con.execute(
                "SELECT * FROM movies WHERE tmdb_id=? AND deleted_at IS NULL",
                (tmdb_id,),
            ).fetchone()
            if row is None:
                return
            updates = {}
            if row["catalog_pending"]:
                updates.update(title=details["title"], catalog_pending=0)
            for key, value in {
                "cast_list": ", ".join(details["cast"]),
                "director": details["director"],
                "overview": details["overview"],
                "genre": details["genre"],
                "year": details["year"],
                "poster_path": details["poster_url"],
                "runtime": details["runtime"],
                "score_percent": details["score_percent"],
            }.items():
                if row[key] in (None, "") and value not in (None, ""):
                    updates[key] = value
            try:
                entities = json.loads(row["entities_json"] or "{}")
                if not isinstance(entities, dict):
                    entities = {}
            except (ValueError, TypeError):
                entities = {}
            merged = dict(details["entities"], **entities)
            old_cast = entities.get("cast")
            if not isinstance(old_cast, list) or len(old_cast) < len(
                details["entities"]["cast"]
            ):
                merged["cast"] = details["entities"]["cast"]
                if details["cast"]:
                    updates["cast_list"] = ", ".join(details["cast"])
            if entities != merged:
                updates["entities_json"] = json.dumps(merged, ensure_ascii=False)
            if updates:
                con.execute(
                    "UPDATE movies SET "
                    + ",".join(key + "=?" for key in updates)
                    + " WHERE id=? AND deleted_at IS NULL",
                    (*updates.values(), row["id"]),
                )

    def schedule(self, movies):
        """Bounded background backfill for the visible page; never delays library UI."""
        if not self.background:
            return set()
        ids = [
            m["tmdb_id"] for m in movies if m.get("tmdb_id") and not m.get("deleted_at")
        ]
        cached = self.cached(ids)
        for movie in movies:
            if movie.get("catalog_pending") and movie.get("tmdb_id") in cached:
                self.fill_missing(movie["tmdb_id"], cached[movie["tmdb_id"]]["details"])
        with self.state_lock:
            for mid in dict.fromkeys(ids):
                if (
                    mid in cached
                    or mid in self.pending
                    or len(self.pending) >= 36
                    or self.retry_at.get(mid, 0) > time.monotonic()
                ):
                    continue
                self.pending.add(mid)
                if self.executor is None:
                    self.executor = ThreadPoolExecutor(
                        max_workers=2, thread_name_prefix="film-metadata"
                    )
                self.executor.submit(self._backfill, mid)
            return self.pending.intersection(ids)

    def _backfill(self, mid):
        try:
            self.fill_missing(mid, self.details(mid))
        except TMDBError:
            # Background scans back off quietly; failed foreground additions can
            # retry after the provider's short cooldown instead of waiting a minute.
            self.retry_at[mid] = max(self.retry_at.get(mid, 0), time.monotonic() + 60)
        finally:
            with self.state_lock:
                self.pending.discard(mid)

    def close(self):
        if self.executor:
            self.executor.shutdown(wait=False, cancel_futures=True)
