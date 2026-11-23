"""Pure, read-only cinema statistics for the active (account or guest) library.

Every figure is computed from active rows only (``deleted_at IS NULL``). Bar sizes
and ring arcs are precomputed as integers so templates can draw SVG charts with
presentation attributes only (no inline ``style`` under the strict CSP).
Personal notes are only counted, never returned.
"""

import json
import re
from datetime import date, timedelta

TOP_GENRES = 8
TOP_PEOPLE = 6
TOP_STUDIOS = 6
TOP_RATED_FILMS = 6
# Actors beyond top billing would turn every ensemble film into noise.
CAST_DEPTH = 10
MAX_RUNTIME = 1000
DATE_PATTERN = re.compile(r"(\d{4})-(\d{2})(?:-(\d{2}))?(?:$|[T ])")
WEEKDAY_LABELS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
RING_CIRCUMFERENCE = 251  # 2 * pi * 40 ≈ 251.33 for SVG completion donut

# Canonical TMDB genre names have UI translations; custom genres stay verbatim.
TMDB_GENRES = frozenset(
    {
        "Action",
        "Adventure",
        "Animation",
        "Comedy",
        "Crime",
        "Documentary",
        "Drama",
        "Family",
        "Fantasy",
        "History",
        "Horror",
        "Music",
        "Mystery",
        "Romance",
        "Science Fiction",
        "TV Movie",
        "Thriller",
        "War",
        "Western",
    }
)

# Turkish plural suffix follows the last spoken word of the decade
# (1990 -> "doksan" -> 'lar, 2020 -> "yirmi" -> 'ler, 1900/2000 -> 'ler).
_TR_DECADE_SUFFIX = {
    0: "ler",
    1: "lar",
    2: "ler",
    3: "lar",
    4: "lar",
    5: "ler",
    6: "lar",
    7: "ler",
    8: "ler",
    9: "lar",
}

COLUMNS = (
    "id,title,poster_path,status,rating,favorite,note,watched_date,year,genre,"
    "runtime,director,cast_list,entities_json,score_percent,order_key"
)


def _rating(value):
    return value if type(value) is int and 1 <= value <= 10 else None


def _average(values):
    return round(sum(values) / len(values), 1) if values else None


def _median(values):
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return round((ordered[mid - 1] + ordered[mid]) / 2, 1)


def _scale(count, peak, minimum=4):
    """0..100 bar size; a non-zero count always stays visible."""
    if not count or not peak:
        return 0
    return max(minimum, min(100, round(count * 100 / peak)))


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def _people(raw_entities, key, fallback, limit=None):
    """[(id_or_None, name)] from saved TMDB credits, else from the text column."""
    people = []
    group = raw_entities.get(key) if isinstance(raw_entities, dict) else None
    if isinstance(group, list):
        for person in group:
            if not isinstance(person, dict):
                continue
            name = _text(person.get("name"))
            if not name:
                continue
            pid = person.get("id")
            people.append((pid if type(pid) is int and pid > 0 else None, name))
    if not people and fallback:
        people = [(None, name.strip()) for name in (fallback or "").split(",")]
        people = [person for person in people if person[1]]
    unique, seen = [], set()
    for pid, name in people:
        marker = pid or name.casefold()
        if marker not in seen:
            seen.add(marker)
            unique.append((pid, name))
    return unique[:limit] if limit else unique


def _entities(value):
    try:
        data = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _rank_entities(tally, limit=TOP_PEOPLE):
    # Credits saved without a TMDB id merge into the one id-bearing entity
    # sharing that name; ambiguous names stay separate rather than guessed.
    by_name = {}
    for key, person in tally.items():
        if key[0] == "id":
            by_name.setdefault(person["name"].casefold(), []).append(key)
    for key in [k for k in tally if k[0] == "name"]:
        matches = by_name.get(key[1], [])
        if len(matches) == 1:
            target = tally[matches[0]]
            source = tally.pop(key)
            target["films"] |= source["films"]
            target["ratings"].update(source["ratings"])
    ranked = []
    for person in tally.values():
        ratings = list(person["ratings"].values())
        ranked.append(
            {
                "id": person["id"],
                "name": person["name"],
                "count": len(person["films"]),
                "avg_rating": _average(ratings),
            }
        )
    ranked.sort(
        key=lambda p: (
            -p["count"],
            -(p["avg_rating"] if p["avg_rating"] is not None else 0),
            p["name"].casefold(),
        )
    )
    return ranked[:limit]


def _tally_entity(tally, eid, name, film, rating):
    key = ("id", eid) if eid else ("name", name.casefold())
    entry = tally.setdefault(
        key, {"id": eid, "name": name, "films": set(), "ratings": {}}
    )
    entry["films"].add(film)
    if rating is not None:
        entry["ratings"][film] = rating


def _longest_streak(dates):
    if not dates:
        return 0
    ordered = sorted(dates)
    best = current = 1
    for prev, curr in zip(ordered, ordered[1:]):
        if curr - prev == timedelta(days=1):
            current += 1
            if current > best:
                best = current
        else:
            current = 1
    return best


def _film_ref(row):
    return {
        "id": row["id"],
        "title": _text(row["title"]) or f"#{row['id']}",
        "year": row["year"] if type(row["year"]) is int else None,
        "runtime": row["runtime"] if type(row["runtime"]) is int else None,
        "rating": _rating(row["rating"]),
        "favorite": row["favorite"] == 1,
        "poster_path": row["poster_path"] or None,
    }


def decade_label_tr(start_year):
    return f"{start_year}'{_TR_DECADE_SUFFIX[(start_year // 10) % 10]}"


def compute_cinema_stats(db, year=None):
    current_year = date.today().year
    year = year if type(year) is int and 1800 <= year <= 2200 else current_year
    rows = db.query(f"SELECT {COLUMNS} FROM movies WHERE deleted_at IS NULL")

    ratings, minutes, runtime_count = [], 0, 0
    totals = dict(
        total=len(rows),
        watched=0,
        watchlist=0,
        favorites=0,
        rated=0,
        with_notes=0,
        watched_this_year=0,
    )
    rating_counts = [0] * 10
    months = [0] * 12
    weekdays = [0] * 7
    runtime_counts = {"short": 0, "feature": 0, "extended": 0, "epic": 0}
    genres, decades = {}, {}
    directors, actors, studios = {}, {}, {}
    seen_years = {current_year, year}
    exact_dates = set()
    tmdb_pairs = []  # (personal_rating, tmdb_rating_10)
    watched_rated_rows = []
    longest_row = shortest_row = oldest_row = newest_row = None

    for index, row in enumerate(rows):
        watched = row["status"] == "Watched"
        rating = _rating(row["rating"])
        totals["watched"] += watched
        totals["watchlist"] += row["status"] == "Watchlist"
        totals["favorites"] += row["favorite"] == 1
        totals["with_notes"] += bool(_text(row["note"]))
        if rating is not None:
            ratings.append(rating)
            rating_counts[rating - 1] += 1
            score_pct = row["score_percent"]
            if type(score_pct) is int and 0 < score_pct <= 100:
                tmdb_pairs.append((rating, score_pct / 10.0))
            if watched:
                watched_rated_rows.append(row)

        match = DATE_PATTERN.match(row["watched_date"] or "") if watched else None
        if match:
            w_year, w_month = int(match[1]), int(match[2])
            if 1800 <= w_year <= 2200:
                seen_years.add(w_year)
            if w_year == year and 1 <= w_month <= 12:
                totals["watched_this_year"] += 1
                months[w_month - 1] += 1
            if match[3]:
                try:
                    exact = date(w_year, w_month, int(match[3]))
                    exact_dates.add(exact)
                    weekdays[exact.weekday()] += 1
                except ValueError:
                    pass

        runtime = row["runtime"]
        if watched and type(runtime) is int and 0 < runtime <= MAX_RUNTIME:
            minutes += runtime
            runtime_count += 1
            if runtime < 90:
                runtime_counts["short"] += 1
            elif runtime < 120:
                runtime_counts["feature"] += 1
            elif runtime < 150:
                runtime_counts["extended"] += 1
            else:
                runtime_counts["epic"] += 1
            if longest_row is None or runtime > longest_row["runtime"]:
                longest_row = row
            if shortest_row is None or runtime < shortest_row["runtime"]:
                shortest_row = row

        names = dict.fromkeys(
            part.strip() for part in (row["genre"] or "").split(",") if part.strip()
        )
        for name in names:
            genre = genres.setdefault(
                name.casefold(), {"name": name, "count": 0, "ratings": []}
            )
            genre["count"] += 1
            if rating is not None:
                genre["ratings"].append(rating)

        released = row["year"]
        if type(released) is int and 1800 <= released <= 2200:
            start = released // 10 * 10
            decades[start] = decades.get(start, 0) + 1
            if oldest_row is None or released < oldest_row["year"]:
                oldest_row = row
            if newest_row is None or released > newest_row["year"]:
                newest_row = row

        if watched:
            entities = _entities(row["entities_json"])
            for pid, name in _people(entities, "directors", row["director"]):
                _tally_entity(directors, pid, name, index, rating)
            for pid, name in _people(entities, "cast", row["cast_list"], CAST_DEPTH):
                _tally_entity(actors, pid, name, index, rating)
            for cid, name in _people(entities, "companies", None):
                _tally_entity(studios, cid, name, index, rating)

    totals.update(
        rated=len(ratings),
        avg_rating=_average(ratings),
        total_minutes=minutes,
        total_hours=minutes // 60,
        runtime_count=runtime_count,
    )

    rating_peak = max(rating_counts)
    month_peak = max(months)
    weekday_peak = max(weekdays)
    runtime_peak = max(runtime_counts.values())
    top_genres = sorted(
        genres.values(), key=lambda g: (-g["count"], g["name"].casefold())
    )[:TOP_GENRES]
    genre_peak = top_genres[0]["count"] if top_genres else 0
    decade_peak = max(decades.values(), default=0)

    completion_pct = round(totals["watched"] * 100 / totals["total"]) if totals["total"] else 0
    favorite_rate = (
        round(totals["favorites"] * 100 / totals["watched"]) if totals["watched"] else 0
    )
    avg_runtime = round(minutes / runtime_count) if runtime_count else None
    total_days = round(minutes / 1440, 1) if minutes else 0.0
    peak_month = (months.index(month_peak) + 1) if month_peak > 0 else None

    critic_delta = None
    tmdb_avg = None
    if tmdb_pairs:
        user_paired_avg = sum(p for p, _ in tmdb_pairs) / len(tmdb_pairs)
        tmdb_paired_avg = sum(t for _, t in tmdb_pairs) / len(tmdb_pairs)
        tmdb_avg = round(tmdb_paired_avg, 1)
        critic_delta = round(user_paired_avg - tmdb_paired_avg, 1)

    top_decade_start = max(decades, key=lambda d: (decades[d], d)) if decades else None

    watched_rated_rows.sort(
        key=lambda r: (
            -(_rating(r["rating"]) or 0),
            -(1 if r["favorite"] == 1 else 0),
            r["order_key"] or "",
        )
    )

    runtime_defs = (
        ("short", "Under 90 min"),
        ("feature", "90–119 min"),
        ("extended", "120–149 min"),
        ("epic", "150+ min"),
    )

    return {
        "year": year,
        "available_years": sorted(seen_years, reverse=True),
        "totals": totals,
        "overview": {
            "completion_pct": completion_pct,
            "completion_ring_dash": round(RING_CIRCUMFERENCE * completion_pct / 100),
            "ring_circumference": RING_CIRCUMFERENCE,
            "favorite_rate": favorite_rate,
            "avg_runtime": avg_runtime,
            "total_days": total_days,
            "median_rating": _median(ratings),
            "ten_count": rating_counts[9],
            "peak_month": peak_month,
            "peak_month_count": month_peak,
            "longest_streak": _longest_streak(exact_dates),
            "tmdb_avg": tmdb_avg,
            "critic_delta": critic_delta,
            "top_genre_name": top_genres[0]["name"] if top_genres else None,
            "top_genre_known": (top_genres[0]["name"] in TMDB_GENRES) if top_genres else False,
            "top_decade": f"{top_decade_start}s" if top_decade_start is not None else None,
            "top_decade_tr": (
                decade_label_tr(top_decade_start) if top_decade_start is not None else None
            ),
        },
        "records": {
            "longest": _film_ref(longest_row) if longest_row else None,
            "shortest": (
                _film_ref(shortest_row)
                if shortest_row and shortest_row["id"] != (longest_row["id"] if longest_row else None)
                else (_film_ref(shortest_row) if shortest_row else None)
            ),
            "oldest": _film_ref(oldest_row) if oldest_row else None,
            "newest": _film_ref(newest_row) if newest_row else None,
        },
        "rating_distribution": [
            {
                "rating": value + 1,
                "count": count,
                "bar_height": _scale(count, rating_peak),
            }
            for value, count in enumerate(rating_counts)
        ],
        "top_genres": [
            {
                "name": genre["name"],
                "known": genre["name"] in TMDB_GENRES,
                "count": genre["count"],
                "avg_rating": _average(genre["ratings"]),
                "bar_width": _scale(genre["count"], genre_peak),
            }
            for genre in top_genres
        ],
        "decades": [
            {
                "decade": f"{start}s",
                "label_tr": decade_label_tr(start),
                "start_year": start,
                "count": decades[start],
                "bar_width": _scale(decades[start], decade_peak),
            }
            for start in sorted(decades)
        ],
        "monthly_activity": [
            {"month": number + 1, "count": count, "bar_height": _scale(count, month_peak)}
            for number, count in enumerate(months)
        ],
        "weekdays": [
            {
                "day": idx,
                "label": WEEKDAY_LABELS[idx],
                "count": count,
                "bar_height": _scale(count, weekday_peak),
            }
            for idx, count in enumerate(weekdays)
        ],
        "runtime_buckets": [
            {
                "key": key,
                "label": label,
                "count": runtime_counts[key],
                "bar_width": _scale(runtime_counts[key], runtime_peak),
            }
            for key, label in runtime_defs
        ],
        "top_directors": _rank_entities(directors, TOP_PEOPLE),
        "top_actors": _rank_entities(actors, TOP_PEOPLE),
        "top_studios": _rank_entities(studios, TOP_STUDIOS),
        "highest_rated": [_film_ref(row) for row in watched_rated_rows[:TOP_RATED_FILMS]],
    }
