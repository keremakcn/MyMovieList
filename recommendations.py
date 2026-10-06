"""Local recommendations from a shared public catalog; private notes are never scored."""

import json
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from itertools import zip_longest
from threading import Lock

from catalog import CatalogService
from recommendation_model import (
    ALGORITHM_VERSION,
    GENRES as GENRES,
    build_profile,
    movie_features,
    profile_fingerprint,
    rank_candidates,
    score_features,
    valid_candidate,
)
from recommendation_model import (
    genre_ids as genre_ids,
)
from tmdb_client import TMDBError, movie_summary

RECENT_LIMIT = 50
POOL_LIMIT = 1200
POOL_PAGES = 20
SESSION_RESERVE = 30
FEATURE_BATCH = 24
PUBLIC_CACHE_TTL = 12 * 60 * 60
PUBLIC_CACHE_KEY = "recommendation_public_catalog_v2"
MODES = {
    "familiar": "Close to my taste",
    "balanced": "A little discovery",
    "explore": "Surprise me",
}


class Recommender:
    def __init__(self, db, tmdb, catalog=None):
        self.db, self.tmdb = db, tmdb
        self.catalog = catalog or CatalogService(db, tmdb, background=False)
        self.session_seed = secrets.token_hex(16)
        self.session_picks = {}
        self.session_profiles = {}
        self.feature_retry = {}
        self.pool_fetched_at = 0
        self.session_lock = Lock()
        self.public_pool = {}
        self.pool_page = 1
        rows = db.query(
            "SELECT value FROM settings WHERE key='recommendation_last_picks'"
        )
        try:
            history = json.loads(rows[0]["value"]) if rows else {}
            self.previous = {
                mode: [mid for mid in ids if type(mid) is int and mid > 0][
                    -RECENT_LIMIT:
                ]
                for mode, ids in history.items()
                if mode in MODES and isinstance(ids, list)
            }
        except (ValueError, TypeError, AttributeError):
            self.previous = {}

        # Only public catalog summaries enter this cache. Old/malformed caches
        # are expendable; personal library records are never changed here.
        rows = db.query("SELECT value FROM settings WHERE key=?", PUBLIC_CACHE_KEY)
        try:
            cached = json.loads(rows[0]["value"]) if rows else {}
            if cached.get("version") == ALGORITHM_VERSION and isinstance(
                cached.get("movies"), list
            ):
                records = cached["movies"][-POOL_LIMIT:]
                self.public_pool = {
                    m["id"]: m for m in records if valid_candidate(m) and "id" in m
                }
                self.pool_page = max(
                    1, min(POOL_PAGES, int(cached.get("next_page", 1)))
                )
                stamp = cached.get("fetched_at", 0)
                self.pool_fetched_at = (
                    stamp
                    if type(stamp) in (int, float) and 0 <= stamp <= time.time()
                    else 0
                )
        except (ValueError, TypeError, AttributeError, OverflowError):
            self.public_pool = {}

    def invalidate(self):
        # Explicitly editing the survey should take effect without a restart.
        with self.session_lock:
            self.session_picks.clear()
            self.session_profiles.clear()

    def library(self):
        rows = self.db.query("""SELECT m.*, CASE WHEN l.movie_id IS NULL THEN 0 ELSE 1 END survey_liked
            FROM movies m LEFT JOIN recommendation_likes l ON l.movie_id=m.id
            WHERE m.deleted_at IS NULL ORDER BY m.id""")
        metadata = self.catalog.cached([m.get("tmdb_id") for m in rows])
        return [
            dict(metadata.get(m.get("tmdb_id"), {}).get("details", {}), **m)
            for m in rows
        ]

    def fetch_groups(self, jobs):
        groups, errors = [], []
        with ThreadPoolExecutor(max_workers=min(4, len(jobs) or 1)) as pool:
            pending = [
                (meta, pool.submit(self.tmdb.get, path, **params))
                for path, params, meta in jobs
            ]
            for meta, future in pending:
                try:
                    data = future.result()
                    rows = data.get("results") if isinstance(data, dict) else None
                    if not isinstance(rows, list):
                        raise TMDBError(
                            "Movie discovery returned an unexpected response. Please try again.",
                            502,
                        )
                    groups.append((rows, meta))
                except TMDBError as exc:
                    errors.append(str(exc))
        return groups, list(dict.fromkeys(errors))

    def discover_params(self, **extra):
        params = dict(
            language="en-US",
            include_adult="false",
            include_video="false",
            **{
                "vote_count.gte": 150,
                "primary_release_date.lte": date.today().isoformat(),
            },
        )
        params.update(extra)
        return params

    def survey_choices(self, query="", page=1, *, language="en-US"):
        if query:
            data = self.tmdb.get(
                "search/movie",
                query=query,
                page=page,
                language=language,
                include_adult="false",
            )
            rows = data.get("results", [])
            pages = min(500, data.get("total_pages", 1))
            errors = []
        else:
            # Fixed breadth, independent of selections: do not steer the survey toward early picks.
            genres = [35, 18, 878, 16, 53, 10749, 99, 12, 27, 80, 14, 36]
            start = ((page - 1) % 2) * 6
            jobs = []
            for slot, genre in enumerate(genres[start : start + 6]):
                params = self.discover_params(
                    with_genres=genre, page=(page + 1) // 2, sort_by="popularity.desc"
                )
                params["language"] = language
                if slot == 1:
                    params["primary_release_date.lte"] = "1999-12-31"
                elif slot == 3:
                    params["with_original_language"] = "ja"
                elif slot == 4:
                    params["with_original_language"] = "ko"
                jobs.append(("discover/movie", params, None))
            groups, errors = self.fetch_groups(jobs)
            rows, seen = [], set()
            for items, _ in groups:
                added = 0
                for item in items:
                    if item["id"] not in seen and not item.get("adult"):
                        seen.add(item["id"])
                        rows.append(item)
                        added += 1
                    if added == 2:
                        break
            pages = 20
        seen = set()
        choices = []
        for row in rows:
            if row["id"] not in seen and not row.get("adult"):
                seen.add(row["id"])
                choices.append(movie_summary(row))
        return choices, pages, errors

    def recommend(self, mode="balanced", *, refresh=False):
        library = self.library()
        profile = build_profile(library)
        fingerprint = profile_fingerprint(profile)
        excluded = {
            m["tmdb_id"]
            for m in self.db.query(
                "SELECT tmdb_id FROM movies WHERE tmdb_id IS NOT NULL"
            )
        }
        excluded.update(
            row["tmdb_id"]
            for row in self.db.query("SELECT tmdb_id FROM recommendation_dismissals")
        )
        with self.session_lock:
            cached = self.session_picks.get(mode)
            errors = []
            if cached is None or refresh:
                previous = {mid for ids in self.previous.values() for mid in ids}
                for picks in self.session_picks.values():
                    previous.update(m["tmdb_id"] for m in picks[:10])
                candidates, errors = self.candidate_pool(refresh=refresh)
                ranked = rank_candidates(
                    list(candidates.values()),
                    profile,
                    excluded,
                    mode,
                    limit=min(SESSION_RESERVE, len(candidates)),
                    previous=previous,
                    seed=secrets.token_hex(16) if refresh else self.session_seed,
                )
                cached = cached if refresh and errors and cached is not None else ranked
                if ranked and not errors:
                    self.session_picks[mode] = ranked
                    self.session_profiles[mode] = fingerprint
            results = [m for m in cached if m["tmdb_id"] not in excluded][:10]
            if cached and len(results) < 10 and not errors:
                # Refill an exhausted reserve without moving visible cards or
                # applying a changed profile to the current session selection.
                candidates, errors = self.candidate_pool()
                reserved = {m["tmdb_id"] for m in cached}
                more = rank_candidates(
                    list(candidates.values()),
                    profile,
                    excluded | reserved,
                    mode,
                    limit=SESSION_RESERVE,
                    previous={mid for ids in self.previous.values() for mid in ids},
                    seed=self.session_seed,
                )
                cached = [m for m in cached if m["tmdb_id"] not in excluded] + more
                if not errors:
                    self.session_picks[mode] = cached
                results = cached[:10]
            if results and not errors:
                ids = [m["tmdb_id"] for m in results]
                old = list(self.previous.get(mode, ()))
                history = ([mid for mid in old if mid not in ids] + ids)[-RECENT_LIMIT:]
                if history != old:
                    self.previous[mode] = history
                    self.db.execute(
                        "INSERT OR REPLACE INTO settings(key,value) VALUES ('recommendation_last_picks',?)",
                        json.dumps(
                            {key: list(value) for key, value in self.previous.items()}
                        ),
                    )

        # Rank saved watchlist movies locally; no online request per library record.
        waiting = []
        for m in library:
            if m["status"] != "Watchlist":
                continue
            features = score_features(movie_features(m), profile)
            score = features["fit"] + 1.8 * features["negative"]
            waiting.append((score, m))
        waiting.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
        return dict(
            movies=results,
            profile=profile,
            waiting=[m for _, m in waiting[:3]],
            errors=errors,
            profile_changed=self.session_profiles.get(mode, fingerprint) != fingerprint,
        )

    def enrich_candidates(self, candidates):
        metadata = self.catalog.cached(list(candidates))
        now = time.monotonic()
        missing = [
            mid
            for mid in candidates
            if metadata.get(mid, {})
            .get("details", {})
            .get("recommendation_features_version")
            != 1
            and self.feature_retry.get(mid, 0) <= now
        ][:FEATURE_BATCH]

        def prepare(mid):
            try:
                return mid, self.catalog.details(mid, features=True)
            except TMDBError:
                return mid, None

        with ThreadPoolExecutor(max_workers=4) as pool:
            for start in range(0, len(missing), 4):
                batch = list(pool.map(prepare, missing[start : start + 4]))
                for mid, details in batch:
                    if details is not None:
                        metadata[mid] = {"details": details}
                    else:
                        self.feature_retry[mid] = now + 60
                if batch and all(details is None for _, details in batch):
                    # An unavailable optional detail service must not turn the
                    # first recommendation load into six timeout batches.
                    for mid in missing[start + 4 :]:
                        self.feature_retry[mid] = now + 60
                    break
        enriched = {}
        for mid, raw in candidates.items():
            details = metadata.get(mid, {}).get("details")
            item = dict(raw)
            if details:
                entities = details["entities"]
                cast, directors = entities.get("cast"), entities.get("directors")
                item.update(
                    entities={
                        "cast": cast[:6] if isinstance(cast, list) else [],
                        "directors": directors if isinstance(directors, list) else [],
                    },
                    keyword_ids=details.get("keyword_ids", []),
                    collection_id=details.get("collection_id"),
                )
            enriched[mid] = item
        return enriched

    def candidate_pool(self, *, refresh=False):
        if (
            self.public_pool
            and not refresh
            and time.time() - self.pool_fetched_at < PUBLIC_CACHE_TTL
        ):
            return dict(self.public_pool), []
        # Every source and metadata request is public and independent of taste.
        # Private ratings, notes, favorite IDs and profile features are never
        # sent as discovery filters or seed IDs to the gateway/provider.
        jobs = []
        for genres in [
            "28|12",
            "35|10749",
            "18|36|10752|37|10770",
            "878|14",
            "16|10751",
            "27|53",
            "99|10402",
            "80|9648",
        ]:
            jobs.append(
                (
                    "discover/movie",
                    self.discover_params(
                        with_genres=genres,
                        page=self.pool_page,
                        sort_by="popularity.desc",
                    ),
                    None,
                )
            )
        jobs.append(
            (
                "discover/movie",
                self.discover_params(
                    with_genres="18|35|80|37",
                    page=self.pool_page,
                    sort_by="vote_average.desc",
                    **{"primary_release_date.lte": "1999-12-31", "vote_count.gte": 80},
                ),
                None,
            )
        )
        languages = ("ja", "ko", "fr", "es", "hi", "tr", "de", "it")
        jobs.append(
            (
                "discover/movie",
                self.discover_params(
                    with_genres="18|35|53|12",
                    page=(self.pool_page - 1) // len(languages) + 1,
                    with_original_language=languages[
                        (self.pool_page - 1) % len(languages)
                    ],
                    sort_by="vote_average.desc",
                    **{"vote_count.gte": 30},
                ),
                None,
            )
        )
        groups, errors = self.fetch_groups(jobs)
        # Interleave sources before metadata enrichment: one popular genre must
        # not monopolize the bounded first-use detail request budget.
        incoming = {}
        for batch in zip_longest(*(rows for rows, _ in groups)):
            for raw in batch:
                if not valid_candidate(raw) or "id" not in raw:
                    continue
                incoming.setdefault(raw["id"], dict(raw))
        candidates = {
            mid: raw for mid, raw in self.public_pool.items() if mid not in incoming
        }
        # Enrich the newest public batch first, including cached metadata for the
        # retained pool. Failed optional metadata never empties the suggestions.
        incoming = self.enrich_candidates(incoming)
        candidates.update(incoming)
        candidates = dict(list(candidates.items())[-POOL_LIMIT:])
        if not errors:
            next_page = self.pool_page % POOL_PAGES + 1
            fetched_at = time.time()
            self.db.execute(
                "INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",
                PUBLIC_CACHE_KEY,
                json.dumps(
                    dict(
                        version=ALGORITHM_VERSION,
                        next_page=next_page,
                        fetched_at=fetched_at,
                        movies=list(candidates.values()),
                    )
                ),
            )
            self.public_pool, self.pool_page, self.pool_fetched_at = (
                candidates,
                next_page,
                fetched_at,
            )
            self.feature_retry = {
                mid: stamp
                for mid, stamp in self.feature_retry.items()
                if mid in candidates
            }
        return candidates, errors
