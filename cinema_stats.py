"""Pure, read-only cinema statistics for the active (account or guest) library.

Every figure is computed from active rows only (``deleted_at IS NULL``). Bar sizes
are precomputed as 0..100 integers so templates can draw SVG ``<rect>`` charts
with presentation attributes only (no inline ``style`` under the strict CSP).
Personal notes are only counted, never returned.
"""

import json
import re
from datetime import date

TOP_GENRES = 8
TOP_PEOPLE = 6
# Actors beyond top billing would turn every ensemble film into noise.
CAST_DEPTH = 10
MAX_RUNTIME = 1000
DATE_PATTERN = re.compile(r"(\d{4})-(\d{2})(?:-\d{2})?(?:$|[T ])")

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
    "status,rating,favorite,note,watched_date,year,genre,runtime,"
    "director,cast_list,entities_json"
)


def _rating(value):
    return value if type(value) is int and 1 <= value <= 10 else None


def _average(values):
    return round(sum(values) / len(values), 1) if values else None


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
    if not people:
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


def _rank_people(tally):
    # Credits saved without a TMDB id merge into the one id-bearing person
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
    return ranked[:TOP_PEOPLE]


def _tally_person(tally, pid, name, film, rating):
    key = ("id", pid) if pid else ("name", name.casefold())
    person = tally.setdefault(
        key, {"id": pid, "name": name, "films": set(), "ratings": {}}
    )
    person["films"].add(film)
    if rating is not None:
        person["ratings"][film] = rating


def decade_label_tr(start_year):
    return f"{start_year}'{_TR_DECADE_SUFFIX[(start_year // 10) % 10]}"


def compute_cinema_stats(db, year=None):
    year = year if type(year) is int and 1800 <= year <= 2200 else date.today().year
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
    genres, decades = {}, {}
    directors, actors = {}, {}

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

        match = DATE_PATTERN.match(row["watched_date"] or "") if watched else None
        if match and int(match[1]) == year and 1 <= int(match[2]) <= 12:
            totals["watched_this_year"] += 1
            months[int(match[2]) - 1] += 1

        runtime = row["runtime"]
        if watched and type(runtime) is int and 0 < runtime <= MAX_RUNTIME:
            minutes += runtime
            runtime_count += 1

        names = dict.fromkeys(
            part.strip() for part in (row["genre"] or "").split(",") if part.strip()
        )
        for name in names:
            genre = genres.setdefault(name.casefold(), {"name": name, "count": 0, "ratings": []})
            genre["count"] += 1
            if rating is not None:
                genre["ratings"].append(rating)

        released = row["year"]
        if type(released) is int and 1800 <= released <= 2200:
            start = released // 10 * 10
            decades[start] = decades.get(start, 0) + 1

        if watched:
            entities = _entities(row["entities_json"])
            for pid, name in _people(entities, "directors", row["director"]):
                _tally_person(directors, pid, name, index, rating)
            for pid, name in _people(entities, "cast", row["cast_list"], CAST_DEPTH):
                _tally_person(actors, pid, name, index, rating)

    totals.update(
        rated=len(ratings),
        avg_rating=_average(ratings),
        total_minutes=minutes,
        total_hours=minutes // 60,
        runtime_count=runtime_count,
    )

    rating_peak = max(rating_counts)
    month_peak = max(months)
    top_genres = sorted(genres.values(), key=lambda g: (-g["count"], g["name"].casefold()))[
        :TOP_GENRES
    ]
    genre_peak = top_genres[0]["count"] if top_genres else 0
    decade_peak = max(decades.values(), default=0)

    return {
        "year": year,
        "totals": totals,
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
        "top_directors": _rank_people(directors),
        "top_actors": _rank_people(actors),
    }
