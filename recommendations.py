"""Local, explainable recommendations. No notes or behavioral telemetry leave the device."""

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import math
import hashlib
import json
import secrets
from threading import Lock
from tmdb_client import TMDBError, movie_summary

GENRES = {
    28: "Action",
    12: "Adventure",
    16: "Animation",
    35: "Comedy",
    80: "Crime",
    99: "Documentary",
    18: "Drama",
    10751: "Family",
    14: "Fantasy",
    36: "History",
    27: "Horror",
    10402: "Music",
    9648: "Mystery",
    10749: "Romance",
    878: "Science Fiction",
    10770: "TV Movie",
    53: "Thriller",
    10752: "War",
    37: "Western",
}
GENRE_IDS = {name.lower(): key for key, name in GENRES.items()}
MODES = {
    "familiar": "Close to my taste",
    "balanced": "A little discovery",
    "explore": "Surprise me",
}


def genre_ids(movie):
    if "genre_ids" in movie:
        return set(movie.get("genre_ids") or [])
    return {
        GENRE_IDS[name.strip().lower()]
        for name in (movie.get("genre") or "").split(",")
        if name.strip().lower() in GENRE_IDS
    }


def build_profile(movies):
    ratings = [m["rating"] for m in movies if m.get("rating") is not None]
    baseline = sum(ratings) / len(ratings) if ratings else 6
    sums, evidence, director_counts = defaultdict(float), defaultdict(float), Counter()
    signals = []
    for movie in movies:
        rating = movie.get("rating")
        # Explicit low scores win over an earlier survey like or favorite.
        if rating is not None:
            signal = max(
                -1, min(1, 0.7 * (rating - 6) / 4 + 0.3 * (rating - baseline) / 3)
            )
            if rating <= 4:
                signal = min(signal, -0.5)
            elif movie.get("favorite"):
                signal = max(signal, 0.8)
        else:
            signal = (
                0.85
                if movie.get("favorite")
                else 0.6
                if movie.get("survey_liked")
                else 0
            )
        if abs(signal) < 0.1:
            continue
        directors = (movie.get("director") or "").strip()
        group = directors or f"film:{movie['id']}"
        director_counts[group] += 1
        # Related films contribute less independent evidence, but never zero.
        ids = genre_ids(movie)
        signals.append(dict(movie=movie, signal=signal, genres=ids, group=group))
    for entry in signals:
        weight = 1 / math.sqrt(director_counts[entry["group"]])
        entry["weight"] = weight
        for genre in entry["genres"]:
            sums[genre] += entry["signal"] * weight
            evidence[genre] += weight
    affinities = {genre: sums[genre] / (evidence[genre] + 4) for genre in sums}
    effective = sum(s["weight"] for s in signals if s["genres"])
    coherence = sum(abs(value) for value in sums.values()) / max(
        1, sum(evidence.values())
    )
    confidence = effective / (effective + 8) * min(1, coherence / 0.5)
    return dict(
        affinities=affinities,
        signals=signals,
        confidence=confidence,
        count=len(signals),
        ready=confidence >= 0.45,
    )


def rank_candidates(
    candidates, profile, excluded=(), mode="balanced", limit=10, previous=(), seed=""
):
    pool = []
    seen = set(excluded)
    for raw in candidates:
        mid = raw["id"]
        if (
            mid in seen
            or raw.get("adult")
            or (raw.get("release_date") or "") > date.today().isoformat()
        ):
            continue
        seen.add(mid)
        genres = genre_ids(raw)
        affinity = sum(profile["affinities"].get(g, 0) for g in genres) / max(
            1, len(genres)
        )
        votes = max(0, raw.get("vote_count") or 0)
        quality = (
            ((raw.get("vote_average") or 0) * votes + 6 * 100) / (votes + 100) / 10
        )
        score = quality * 0.3 + affinity * 2
        # Small session variation; preference fit and diversity remain dominant.
        if seed:
            digest = hashlib.sha256(f"{seed}:{mid}".encode()).digest()
            score += int.from_bytes(digest[:4], "big") / (2**32) * 0.1
        if mid in previous:
            score -= 0.45
        if affinity > 0.05:
            genre = max(genres, key=lambda g: profile["affinities"].get(g, 0))
            evidence = [
                s
                for s in profile["signals"]
                if s["signal"] > 0 and genre in s["genres"]
            ]
            liked = max(evidence, key=lambda s: s["signal"])["movie"]["title"]
            reason = (
                f"Shares {GENRES.get(genre, 'a genre')} with {liked}, a film you liked."
            )
        else:
            reason = (
                "A discovery pick to broaden your selection."
                if profile["count"]
                else "A starting point while we learn your taste."
            )
        pool.append(
            dict(
                raw=raw,
                score=score,
                genres=genres,
                reason=reason,
            )
        )
    selected = []
    diversity = {"familiar": 0.25, "balanced": 0.6, "explore": 1.0}.get(mode, 0.6)
    # Low confidence gives variety more influence, never a single-film taste lock.
    diversity += (1 - profile["confidence"]) * 0.2
    while pool and len(selected) < limit:

        def adjusted(item):
            overlap = max(
                (
                    len(item["genres"] & p["genres"])
                    / max(1, len(item["genres"] | p["genres"]))
                    for p in selected
                ),
                default=0,
            )
            genre_repeats = max(
                (sum(g in p["genres"] for p in selected) for g in item["genres"]),
                default=0,
            )
            return item["score"] - diversity * overlap - 0.09 * genre_repeats

        best = max(pool, key=lambda item: (adjusted(item), -item["raw"]["id"]))
        pool.remove(best)
        selected.append(best)
    return [
        dict(movie_summary(item["raw"]), reason=item["reason"]) for item in selected
    ]


class Recommender:
    def __init__(self, db, tmdb):
        self.db, self.tmdb = db, tmdb
        self.session_seed = secrets.token_hex(16)
        self.session_picks = {}
        self.session_lock = Lock()
        rows = db.query(
            "SELECT value FROM settings WHERE key='recommendation_last_picks'"
        )
        try:
            history = json.loads(rows[0]["value"]) if rows else {}
            self.previous = {
                mode: set(ids)
                for mode, ids in history.items()
                if mode in MODES and isinstance(ids, list)
            }
        except (ValueError, TypeError, AttributeError):
            self.previous = {}

    def invalidate(self):
        # Explicitly editing the survey should take effect without a restart.
        with self.session_lock:
            self.session_picks.clear()

    def library(self):
        return self.db.query("""SELECT m.*, CASE WHEN l.movie_id IS NULL THEN 0 ELSE 1 END survey_liked
            FROM movies m LEFT JOIN recommendation_likes l ON l.movie_id=m.id
            WHERE m.deleted_at IS NULL ORDER BY m.id""")

    def fetch_groups(self, jobs):
        groups, errors = [], []
        with ThreadPoolExecutor(max_workers=min(4, len(jobs) or 1)) as pool:
            pending = [
                (meta, pool.submit(self.tmdb.get, path, **params))
                for path, params, meta in jobs
            ]
            for meta, future in pending:
                try:
                    groups.append((future.result().get("results", []), meta))
                except TMDBError as exc:
                    errors.append(str(exc))
        return groups, list(dict.fromkeys(errors))

    def discover_params(self, **extra):
        return dict(
            language="en-US",
            include_adult="false",
            include_video="false",
            **{
                "vote_count.gte": 150,
                "primary_release_date.lte": date.today().isoformat(),
            },
            **extra,
        )

    def survey_choices(self, query="", page=1):
        if query:
            data = self.tmdb.get(
                "search/movie",
                query=query,
                page=page,
                language="en-US",
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

    def recommend(self, mode="balanced"):
        library = self.library()
        profile = build_profile(library)
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
            if cached is None:
                candidates, errors = self.candidate_pool()
                ranked = rank_candidates(
                    list(candidates.values()),
                    profile,
                    excluded,
                    mode,
                    limit=len(candidates),
                    previous=self.previous.get(mode, set()),
                    seed=self.session_seed,
                )
                cached = ranked
                if ranked and not errors:
                    self.session_picks[mode] = ranked
                    # Only the last ten picks per mode are retained locally, not an activity log.
                    with self.db.connect(write=True) as con:
                        stored = con.execute(
                            "SELECT value FROM settings WHERE key='recommendation_last_picks'"
                        ).fetchone()
                        try:
                            history = json.loads(stored["value"]) if stored else {}
                            if not isinstance(history, dict):
                                history = {}
                        except (ValueError, TypeError):
                            history = {}
                        history = {
                            key: value for key, value in history.items() if key in MODES
                        }
                        history[mode] = [m["tmdb_id"] for m in ranked[:10]]
                        con.execute(
                            "INSERT OR REPLACE INTO settings(key,value) VALUES ('recommendation_last_picks',?)",
                            (json.dumps(history),),
                        )
            results = [m for m in cached if m["tmdb_id"] not in excluded][:10]

        # Rank saved watchlist movies locally; no online request per library record.
        waiting = []
        for m in library:
            if m["status"] != "Watchlist":
                continue
            genres = genre_ids(m)
            score = sum(profile["affinities"].get(g, 0) for g in genres) / max(
                1, len(genres)
            )
            waiting.append((score, m))
        waiting.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
        return dict(
            movies=results,
            profile=profile,
            waiting=[m for _, m in waiting[:3]],
            errors=errors,
        )

    def candidate_pool(self):
        # Public candidate pool is identical for every user; no taste-derived
        # movie IDs, genres, scores or favorites are sent to TMDB.
        jobs = []
        for genres in [
            "28|12",
            "35|10749",
            "18|36",
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
                        with_genres=genres, page=1, sort_by="popularity.desc"
                    ),
                    None,
                )
            )
        groups, errors = self.fetch_groups(jobs)
        candidates = {}
        for rows, _ in groups:
            for raw in rows:
                candidates.setdefault(raw["id"], dict(raw))
        return candidates, errors
