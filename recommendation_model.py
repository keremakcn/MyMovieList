"""Pure local preference modelling and list selection; never reads private notes.

Feature IDs stay independent of display language. Evidence is regularized and
related films are discounted. List selection balances relevance, the user's
different interests, repeated themes, franchises and recent exposure.
"""

import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import date

from tmdb_client import movie_summary

ALGORITHM_VERSION = "2"
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
FEATURE_WEIGHTS = {
    "genres": 0.34,
    "keywords": 0.30,
    "directors": 0.19,
    "cast": 0.11,
    "decades": 0.04,
    "languages": 0.02,
}
FEATURE_PRIORS = {
    "genres": 4,
    "keywords": 5,
    "directors": 3,
    "cast": 5,
    "decades": 8,
    "languages": 8,
}
CAST_LIMIT = 6
POLICIES = {
    "familiar": dict(fit=2.0, novelty=0.08, familiar_slots=8, diversity=0.20),
    "balanced": dict(fit=1.35, novelty=0.32, familiar_slots=5, diversity=0.40),
    "explore": dict(fit=0.80, novelty=0.58, familiar_slots=2, diversity=0.60),
}


def positive_ids(values):
    if not isinstance(values, (list, tuple, set, frozenset)):
        return frozenset()
    return frozenset(
        value for value in (values or []) if type(value) is int and value > 0
    )


def valid_candidate(raw):
    """Malformed public summaries are expendable, never personal records."""
    if not isinstance(raw, dict):
        return False
    mid = raw.get("id", raw.get("tmdb_id"))
    if type(mid) is not int or mid < 1 or not isinstance(raw.get("title"), str):
        return False
    if raw.get("adult") or not isinstance(raw.get("genre_ids", []), list):
        return False
    if type(raw.get("vote_count", 0)) is not int or raw.get("vote_count", 0) < 0:
        return False
    average = raw.get("vote_average", 0)
    if (
        type(average) not in (int, float)
        or not math.isfinite(average)
        or not 0 <= average <= 10
    ):
        return False
    released = raw.get("release_date") or ""
    try:
        if released and (
            not isinstance(released, str)
            or date.fromisoformat(released).isoformat() != released
        ):
            return False
    except ValueError:
        return False
    return True


def genre_ids(movie):
    ids = positive_ids(movie.get("genre_ids")) & GENRES.keys()
    if ids:
        return ids
    return frozenset(
        GENRE_IDS[name.strip().lower()]
        for name in (movie.get("genre") or "").split(",")
        if name.strip().lower() in GENRE_IDS
    )


def movie_features(movie):
    entities = movie.get("entities")
    if not isinstance(entities, dict):
        try:
            entities = json.loads(movie.get("entities_json") or "{}")
        except (ValueError, TypeError):
            entities = {}
    if not isinstance(entities, dict):
        entities = {}

    def people(group, limit=None):
        result = []
        people_list = entities.get(group)
        for person in people_list if isinstance(people_list, list) else []:
            if not isinstance(person, dict):
                continue
            pid = person.get("id")
            if type(pid) is int and pid > 0 and pid not in result:
                result.append(pid)
                if limit and len(result) == limit:
                    break
        return frozenset(result)

    directors = people("directors")
    if not directors:
        # Canonical English legacy fields remain useful before metadata backfill.
        directors = frozenset(
            "legacy:" + name.strip().casefold()
            for name in (movie.get("director") or "").split(",")
            if name.strip()
        )
    year = movie.get("year")
    if not year:
        release = movie.get("release_date") or ""
        year = int(release[:4]) if release[:4].isdigit() else None
    language = movie.get("original_language")
    collection = movie.get("collection_id")
    return dict(
        genres=genre_ids(movie),
        keywords=positive_ids(movie.get("keyword_ids")),
        directors=directors,
        cast=people("cast", CAST_LIMIT),
        decades=frozenset([year // 10 * 10])
        if type(year) is int and 1880 <= year <= date.today().year
        else frozenset(),
        languages=frozenset([language])
        if isinstance(language, str) and len(language) == 2
        else frozenset(),
        collection=collection if type(collection) is int and collection > 0 else None,
    )


def preference_signal(movie, baseline):
    rating = movie.get("rating")
    if rating is not None:
        signal = max(-1, min(1, 0.7 * (rating - 6) / 4 + 0.3 * (rating - baseline) / 3))
        if rating <= 4:
            return min(signal, -0.5)
        return max(signal, 0.8) if movie.get("favorite") else signal
    if movie.get("favorite"):
        return 0.85
    return 0.6 if movie.get("survey_liked") else 0


def build_profile(movies):
    ratings = [m["rating"] for m in movies if m.get("rating") is not None]
    baseline = sum(ratings) / len(ratings) if ratings else 6
    signals, related = [], Counter()
    for movie in movies:
        signal = preference_signal(movie, baseline)
        if abs(signal) < 0.1:
            continue
        features = movie_features(movie)
        group = (
            ("collection", features["collection"])
            if features["collection"]
            else ("directors", tuple(sorted(features["directors"], key=str)))
            if features["directors"]
            else ("film", movie.get("tmdb_id") or movie.get("id"))
        )
        related[group] += 1
        signals.append(
            dict(
                movie=movie,
                signal=signal,
                genres=features["genres"],
                features=features,
                group=group,
            )
        )
    sums = {group: defaultdict(float) for group in FEATURE_WEIGHTS}
    supports = {group: defaultdict(float) for group in FEATURE_WEIGHTS}
    magnitudes = {group: defaultdict(float) for group in FEATURE_WEIGHTS}
    hits = {group: Counter() for group in FEATURE_WEIGHTS}
    interests, themes, positive_mass = defaultdict(float), defaultdict(float), 0.0
    effective = 0.0
    for entry in signals:
        weight = 1 / math.sqrt(related[entry["group"]])
        entry["weight"] = weight
        if any(entry["features"][group] for group in FEATURE_WEIGHTS):
            effective += weight
        for group in FEATURE_WEIGHTS:
            tokens = entry["features"][group]
            token_weight = weight / math.sqrt(max(1, len(tokens)))
            for token in tokens:
                sums[group][token] += entry["signal"] * token_weight
                supports[group][token] += token_weight
                magnitudes[group][token] += abs(entry["signal"]) * token_weight
                hits[group][token] += 1
        if entry["signal"] > 0:
            mass = entry["signal"] * weight
            positive_mass += mass
            for genre in entry["genres"]:
                interests[genre] += mass / max(1, len(entry["genres"]))
            for keyword in entry["features"]["keywords"]:
                themes[keyword] += mass
    affinities = {
        group: {
            token: value / (supports[group][token] + FEATURE_PRIORS[group])
            for token, value in sums[group].items()
        }
        for group in FEATURE_WEIGHTS
    }
    agreement = sum(
        FEATURE_WEIGHTS[g] * sum(abs(v) for v in sums[g].values())
        for g in FEATURE_WEIGHTS
    )
    magnitude = sum(
        FEATURE_WEIGHTS[g] * sum(magnitudes[g].values()) for g in FEATURE_WEIGHTS
    )
    agreement = agreement / magnitude if magnitude else 0
    # Confidence measures usable evidence and agreement, not rating enthusiasm.
    confidence = effective / (effective + 8) * (0.4 + 0.6 * agreement)
    total_interests = sum(interests.values())
    return dict(
        affinities=affinities["genres"],
        features=affinities,
        supports=supports,
        hits=hits,
        signals=signals,
        confidence=confidence,
        count=len(signals),
        ready=confidence >= 0.45,
        interests={g: value / total_interests for g, value in interests.items()}
        if total_interests
        else {},
        themes={k: value / positive_mass for k, value in themes.items()}
        if positive_mass
        else {},
        baseline=baseline,
        algorithm_version=ALGORITHM_VERSION,
    )


def profile_fingerprint(profile):
    # Neither notes, localized titles nor UI settings affect recommendation identity.
    items = []
    for entry in profile["signals"]:
        features = entry["features"]
        items.append(
            (
                entry["movie"].get("tmdb_id") or entry["movie"].get("id"),
                round(entry["signal"], 8),
                [(g, sorted(features[g], key=str)) for g in FEATURE_WEIGHTS],
                features["collection"],
            )
        )
    return hashlib.sha256(
        json.dumps(sorted(items, key=lambda x: x[0]), sort_keys=True).encode()
    ).hexdigest()


def score_features(features, profile):
    affinities = profile["features"]
    active = sum(FEATURE_WEIGHTS[g] for g in FEATURE_WEIGHTS if affinities[g]) or 1
    fit, negative, familiarity, matched_weight = 0.0, 0.0, 0.0, 0.0
    for group, weight in FEATURE_WEIGHTS.items():
        tokens = features[group]
        if not tokens or not affinities[group]:
            continue
        values = [affinities[group].get(token, 0) for token in tokens]
        # A matching director or lead should not be drowned out by other credits.
        positive = (
            max(max(values), 0)
            if group in ("directors", "cast")
            else sum(max(0, v) for v in values) / len(values)
        )
        fit += weight * positive
        negative += weight * sum(min(0, v) for v in values) / len(values)
        familiarity += weight * sum(v > 0.05 for v in values) / len(values)
        matched_weight += weight
    return dict(
        fit=fit / active,
        negative=negative / active,
        familiarity=familiarity / matched_weight if matched_weight else 0,
    )


def feature_similarity(left, right):
    total, weight = 0.0, 0.0
    for group in ("genres", "keywords", "directors", "cast"):
        a, b = left[group], right[group]
        if not a or not b:
            continue
        w = FEATURE_WEIGHTS[group]
        total += w * len(a & b) / len(a | b)
        weight += w
    return total / weight if weight else 0


def rank_candidates(
    candidates, profile, excluded=(), mode="balanced", limit=10, previous=(), seed=""
):
    policy = POLICIES.get(mode, POLICIES["balanced"])
    familiar_slots = policy["familiar_slots"]
    if not profile["ready"] and mode == "familiar":
        familiar_slots = 6
    pool, seen, recent = [], set(excluded), set(previous)
    positive_genres = {g for g, v in profile["affinities"].items() if v > 0.05}
    rich_evidence = any(
        value >= 0.15
        for group in ("keywords", "directors", "cast")
        for value in profile["features"][group].values()
    )
    strongest = {}
    for entry in profile["signals"]:
        if entry["signal"] > 0:
            for genre in entry["genres"]:
                if (
                    genre not in strongest
                    or entry["signal"] > strongest[genre]["signal"]
                ):
                    strongest[genre] = entry
    for raw in candidates:
        if not valid_candidate(raw):
            continue
        mid = raw.get("id", raw.get("tmdb_id"))
        if (
            type(mid) is not int
            or mid < 1
            or mid in seen
            or raw.get("adult")
            or (raw.get("release_date") or "") > date.today().isoformat()
        ):
            continue
        seen.add(mid)
        features = movie_features(raw)
        scored = score_features(features, profile)
        # Repeated negative evidence is not a novelty source. Mixed evidence
        # remains eligible: disliking one thriller is not a ban on thrillers.
        strongly_negative = any(
            profile["features"][group].get(token, 0) < -0.35
            and profile["hits"][group].get(token, 0) >= 3
            for group in ("genres", "keywords")
            for token in features[group]
        )
        if strongly_negative and scored["fit"] < 0.05:
            continue
        votes = max(0, raw.get("vote_count") or 0)
        quality = (
            ((raw.get("vote_average") or 0) * votes + 6 * 100) / (votes + 100)
        ) / 10
        score = (
            0.45 * quality + policy["fit"] * scored["fit"] + 1.8 * scored["negative"]
        )
        score += policy["novelty"] * (1 - scored["familiarity"])
        if seed:
            digest = hashlib.sha256(f"{seed}:{mode}:{mid}".encode()).digest()
            score += int.from_bytes(digest[:4], "big") / 2**32 * 0.035
        genre_familiarity = len(features["genres"] & positive_genres) / max(
            1, len(features["genres"])
        )
        rich_match = any(
            profile["features"][group].get(token, 0) >= 0.15
            for group in ("keywords", "directors", "cast")
            for token in features[group]
        )
        familiar = (
            genre_familiarity >= 0.5
            and (not rich_evidence or scored["familiarity"] >= 0.65)
            or rich_match
            and scored["fit"] >= 0.10
            and scored["familiarity"] >= 0.35
        )
        evidence = [strongest[g] for g in features["genres"] if g in strongest]
        liked = (
            max(evidence, key=lambda s: s["signal"])["movie"].get(
                "title", "a film you liked"
            )
            if evidence
            else None
        )
        reason = (
            f"Shares an interest with {liked}."
            if liked
            else "A discovery pick to broaden your selection."
        )
        pool.append(
            dict(
                raw=dict(raw, id=mid),
                score=score,
                features=features,
                familiar=familiar,
                recent=mid in recent,
                overlap=0.0,
                reason=reason,
            )
        )
    selected, directors, collections, keywords = [], Counter(), Counter(), Counter()
    interests, familiar_count = Counter(), 0
    while pool and len(selected) < limit:
        eligible = [p for p in pool if not p["recent"]] or pool
        # Soft caps relax only when the remaining pool cannot supply alternatives.
        unconcentrated = []
        for item in eligible:
            features = item["features"]
            collection_full = (
                features["collection"] and collections[features["collection"]] >= 1
            )
            director_full = any(directors[d] >= 2 for d in features["directors"])
            theme_full = any(
                keywords[k] >= max(2, math.ceil(10 * profile["themes"].get(k, 0) + 1))
                for k in features["keywords"]
            )
            if not (collection_full or director_full or theme_full):
                unconcentrated.append(item)
        eligible = unconcentrated or eligible
        slot = len(selected) % 10
        offset = 10 - familiar_slots
        want_familiar = ((slot + 1) * familiar_slots + offset) // 10 > (
            slot * familiar_slots + offset
        ) // 10
        lane = [item for item in eligible if item["familiar"] == want_familiar]
        if positive_genres and lane:
            eligible = lane
        # Weighted round-robin preserves smaller positive interests as the
        # familiar portion grows. Multi-genre films contribute fractional mass.
        if want_familiar and positive_genres:
            available = {
                g
                for item in eligible
                if item["familiar"]
                for g in item["features"]["genres"] & positive_genres
            }
            if available:
                target = max(
                    available,
                    key=lambda g: (
                        profile["interests"].get(g, 0) * (familiar_count + 1)
                        - interests[g],
                        -g,
                    ),
                )
                matching = [
                    item
                    for item in eligible
                    if item["familiar"] and target in item["features"]["genres"]
                ]
                if matching:
                    eligible = matching
        best = max(
            eligible,
            key=lambda item: (
                item["score"] - policy["diversity"] * item["overlap"],
                -item["raw"]["id"],
            ),
        )
        pool.remove(best)
        selected.append(best)
        features = best["features"]
        directors.update(features["directors"])
        keywords.update(features["keywords"])
        if features["collection"]:
            collections[features["collection"]] += 1
        if best["familiar"]:
            familiar_count += 1
            genres = features["genres"] & positive_genres
            for genre in genres:
                interests[genre] += 1 / max(1, len(genres))
        for item in pool:
            item["overlap"] = max(
                item["overlap"], feature_similarity(item["features"], features)
            )
    return [
        dict(movie_summary(item["raw"]), reason=item["reason"]) for item in selected
    ]
