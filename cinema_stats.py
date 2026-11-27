"""Pure, read-only cinema statistics for the active (account or guest) library.

Every figure is computed from active rows only (``deleted_at IS NULL``). Bar sizes
and ring arcs are precomputed as integers so templates can draw SVG charts with
presentation attributes only (no inline ``style`` under the strict CSP).
Personal notes are only counted, never returned.
"""

import json
import math
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


def _build_genre_radar(top_genres):
    """Precompute a 6-axis hexagonal SVG radar/constellation chart (CSP-safe, no inline CSS)."""
    cx, cy, radius = 140, 140, 88
    canonical_pad = [
        "Drama",
        "Science Fiction",
        "Thriller",
        "Comedy",
        "Action",
        "Romance",
    ]
    axes_source = [dict(g) for g in top_genres[:6]]
    existing_names = {g["name"].casefold() for g in axes_source}
    for fallback_name in canonical_pad:
        if len(axes_source) >= 6:
            break
        if fallback_name.casefold() not in existing_names:
            existing_names.add(fallback_name.casefold())
            axes_source.append(
                {
                    "name": fallback_name,
                    "known": True,
                    "count": 0,
                    "avg_rating": None,
                    "bar_width": 0,
                }
            )
    peak = max((g["count"] for g in axes_source), default=0)
    rings = []
    for pct in (0.33, 0.66, 1.0):
        pts = []
        for idx in range(6):
            angle = -math.pi / 2 + idx * (2 * math.pi / 6)
            rx = round(cx + math.cos(angle) * radius * pct, 1)
            ry = round(cy + math.sin(angle) * radius * pct, 1)
            pts.append(f"{rx},{ry}")
        rings.append(" ".join(pts))

    axes = []
    poly_pts = []
    for idx, item in enumerate(axes_source):
        angle = -math.pi / 2 + idx * (2 * math.pi / 6)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        x2 = round(cx + cos_a * radius, 1)
        y2 = round(cy + sin_a * radius, 1)
        lx = round(cx + cos_a * (radius + 24), 1)
        ly = round(cy + sin_a * (radius + 18), 1)
        ratio = (max(0.14, item["count"] / peak) if item["count"] > 0 and peak > 0 else 0.06)
        dx = round(cx + cos_a * radius * ratio, 1)
        dy = round(cy + sin_a * radius * ratio, 1)
        poly_pts.append(f"{dx},{dy}")
        anchor = "middle" if abs(cos_a) < 0.25 else ("start" if cos_a > 0 else "end")
        axes.append(
            {
                "name": item["name"],
                "known": bool(item.get("known")),
                "count": item["count"],
                "avg_rating": item.get("avg_rating"),
                "x2": x2,
                "y2": y2,
                "lx": lx,
                "ly": ly,
                "anchor": anchor,
                "dot_x": dx,
                "dot_y": dy,
            }
        )
    return {
        "rings": rings,
        "axes": axes,
        "polygon": " ".join(poly_pts),
        "has_data": peak > 0,
    }


def _build_watch_heatmap(year, daily_counts):
    """Precompute a 53-week x 7-day SVG screening heatmap for ``year``."""
    start_jan = date(year, 1, 1)
    end_dec = date(year, 12, 31)
    grid_start = start_jan - timedelta(days=start_jan.weekday())
    peak = max(daily_counts.values(), default=0)
    cells = []
    month_markers = []
    seen_months = set()
    cursor = grid_start
    col = 0
    while cursor <= end_dec and col < 54:
        for dow in range(7):
            current = cursor + timedelta(days=dow)
            if current.year == year:
                iso_d = current.isoformat()
                cnt = daily_counts.get(iso_d, 0)
                if cnt == 0:
                    lvl = 0
                elif peak <= 1:
                    lvl = 4
                else:
                    lvl = min(4, max(1, math.ceil(cnt * 4 / peak)))
                if current.day <= 7 and current.month not in seen_months:
                    seen_months.add(current.month)
                    month_markers.append({"month": current.month, "x": 28 + col * 13})
                cells.append(
                    {
                        "date": iso_d,
                        "count": cnt,
                        "level": lvl,
                        "x": 28 + col * 13,
                        "y": 18 + dow * 13,
                    }
                )
        cursor += timedelta(days=7)
        col += 1
    peak_date = max(daily_counts, key=lambda k: (daily_counts[k], k)) if daily_counts else None
    return {
        "width": 28 + col * 13 + 8,
        "height": 18 + 7 * 13 + 6,
        "cells": cells,
        "month_markers": month_markers,
        "active_days": len(daily_counts),
        "peak_date": peak_date,
        "peak_count": daily_counts.get(peak_date, 0) if peak_date else 0,
    }


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
    daily_counts = {}
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
                    if w_year == year:
                        iso_day = exact.isoformat()
                        daily_counts[iso_day] = daily_counts.get(iso_day, 0) + 1
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
        "genre_radar": _build_genre_radar(
            [
                {
                    "name": genre["name"],
                    "known": genre["name"] in TMDB_GENRES,
                    "count": genre["count"],
                    "avg_rating": _average(genre["ratings"]),
                }
                for genre in top_genres
            ]
        ),
        "watch_heatmap": _build_watch_heatmap(year, daily_counts),
    }


def _monogram(name):
    """Build a crisp 2-3 character studio/person monogram (e.g. 'Warner Bros.' -> 'WB', 'A24' -> 'A24')."""
    cleaned = _text(name)
    if not cleaned:
        return "◈"
    parts = [p for p in re.split(r"[\s\-/&·]+", cleaned) if p]
    if len(parts) == 1:
        token = re.sub(r"[^A-Za-z0-9ÇĞİÖŞÜçğıöşü]", "", parts[0])
        return (token[:3] if len(token) <= 3 else token[:2]).upper() or "◈"
    skip = {"the", "of", "and", "pictures", "productions", "films", "film", "studios", "studio", "entertainment", "company", "inc", "llc"}
    meaningful = [p for p in parts if p.casefold().rstrip(".") not in skip] or parts
    letters = "".join(
        re.sub(r"[^A-Za-z0-9ÇĞİÖŞÜçğıöşü]", "", p)[:1] for p in meaningful[:2]
    )
    return letters.upper() or cleaned[:2].upper()


def _safe_media_url(value):
    if not isinstance(value, str):
        return None
    v = value.strip()
    if v.startswith(("https://image.tmdb.org/t/p/", "/static/")):
        return v
    return None


def _build_monthly_wave(monthly_activity):
    """Precompute smooth cubic Bezier SVG wave coordinates for 12-month watch cadence."""
    width = 560.0
    pad_l, pad_r = 26.0, 26.0
    top_y, baseline = 28.0, 144.0
    span_x = width - pad_l - pad_r
    span_y = baseline - top_y
    peak = max((item["count"] for item in monthly_activity), default=0)

    points = []
    for idx, item in enumerate(monthly_activity):
        x = round(pad_l + (idx / 11.0) * span_x, 1)
        count = item["count"]
        ratio = (count / peak) if peak > 0 else 0.0
        y = round(baseline - ratio * span_y, 1)
        points.append(
            {
                "month": item["month"],
                "count": count,
                "x": x,
                "y": y,
                "is_peak": peak > 0 and count == peak,
            }
        )

    if not points:
        return {
            "width": int(width),
            "height": 172,
            "baseline": int(baseline),
            "grid_lines": [36, 72, 108],
            "points": [],
            "line_path": "",
            "area_path": "",
            "has_data": False,
        }

    # Monotone-clamped cubic Bezier spline so zero months stay flat on the baseline.
    cmds = [f"M {points[0]['x']},{points[0]['y']}"]
    for i in range(len(points) - 1):
        p0 = points[i]
        p1 = points[i + 1]
        dx = (p1["x"] - p0["x"]) * 0.42
        c1x = round(p0["x"] + dx, 1)
        c1y = p0["y"]
        c2x = round(p1["x"] - dx, 1)
        c2y = p1["y"]
        cmds.append(f"C {c1x},{c1y} {c2x},{c2y} {p1['x']},{p1['y']}")

    line_path = " ".join(cmds)
    area_path = (
        f"{line_path} L {points[-1]['x']},{baseline} "
        f"L {points[0]['x']},{baseline} Z"
    )
    return {
        "width": int(width),
        "height": 172,
        "baseline": int(baseline),
        "grid_lines": [36, 72, 108],
        "points": points,
        "line_path": line_path,
        "area_path": area_path,
        "has_data": peak > 0,
    }


def build_stats_view_extras(db, stats):
    """Build privacy-safe view extras for /stats (posters, portraits, drilldowns, wave chart).

    Personal notes are NEVER selected or included. ``compute_cinema_stats`` output
    remains untouched so all pure stats schema contracts stay intact.
    """
    year = stats["year"]
    rows = db.query(
        "SELECT id,title,poster_path,status,rating,favorite,watched_date,year,genre,"
        "runtime,director,cast_list,entities_json "
        "FROM movies WHERE deleted_at IS NULL"
    )

    by_date = {}
    by_month = {str(m): [] for m in range(1, 13)}
    by_weekday = {str(d): [] for d in range(7)}
    by_rating = {str(r): [] for r in range(1, 11)}
    by_genre = {}
    by_decade = {}
    by_runtime = {"short": [], "feature": [], "extended": [], "epic": []}

    person_portraits = {}
    studio_posters = {}
    studio_logos = {}

    genre_canonical = {
        g["name"].casefold(): g["name"] for g in (stats.get("top_genres") or [])
    }

    for row in rows:
        watched = row["status"] == "Watched"
        rating = _rating(row["rating"])
        film = {
            "id": row["id"],
            "title": _text(row["title"]) or f"#{row['id']}",
            "year": row["year"] if type(row["year"]) is int else None,
            "runtime": row["runtime"] if type(row["runtime"]) is int else None,
            "rating": rating,
            "favorite": row["favorite"] == 1,
            "poster_path": row["poster_path"] or None,
            "watched_date": _text(row["watched_date"]) or None,
            "status": row["status"] or "Watchlist",
        }

        if rating is not None:
            by_rating[str(rating)].append(film)

        match = DATE_PATTERN.match(row["watched_date"] or "") if watched else None
        if match:
            w_year, w_month = int(match[1]), int(match[2])
            if w_year == year and 1 <= w_month <= 12:
                by_month[str(w_month)].append(film)
            if match[3]:
                try:
                    exact = date(w_year, w_month, int(match[3]))
                    by_weekday[str(exact.weekday())].append(film)
                    if w_year == year:
                        by_date.setdefault(exact.isoformat(), []).append(film)
                except ValueError:
                    pass

        runtime = row["runtime"]
        if watched and type(runtime) is int and 0 < runtime <= MAX_RUNTIME:
            if runtime < 90:
                by_runtime["short"].append(film)
            elif runtime < 120:
                by_runtime["feature"].append(film)
            elif runtime < 150:
                by_runtime["extended"].append(film)
            else:
                by_runtime["epic"].append(film)

        for part in dict.fromkeys(
            p.strip() for p in (row["genre"] or "").split(",") if p.strip()
        ):
            canonical = genre_canonical.get(part.casefold(), part)
            by_genre.setdefault(canonical, []).append(film)

        released = row["year"]
        if type(released) is int and 1800 <= released <= 2200:
            decade_key = f"{released // 10 * 10}s"
            by_decade.setdefault(decade_key, []).append(film)

        entities = _entities(row["entities_json"])
        for group_key in ("directors", "cast"):
            group = entities.get(group_key)
            if isinstance(group, list):
                for item in group:
                    if not isinstance(item, dict):
                        continue
                    portrait = _safe_media_url(item.get("portrait_url"))
                    if not portrait:
                        continue
                    pid = item.get("id")
                    if type(pid) is int and pid > 0:
                        person_portraits.setdefault(str(pid), portrait)
                    pname = _text(item.get("name"))
                    if pname:
                        person_portraits.setdefault(pname.casefold(), portrait)

        if watched:
            companies = entities.get("companies")
            if isinstance(companies, list):
                for comp in companies:
                    if not isinstance(comp, dict):
                        continue
                    cid = comp.get("id")
                    cname = _text(comp.get("name"))
                    logo = _safe_media_url(comp.get("logo_url"))
                    keys = []
                    if type(cid) is int and cid > 0:
                        keys.append(str(cid))
                    if cname:
                        keys.append(cname.casefold())
                    for key in keys:
                        if logo:
                            studio_logos.setdefault(key, logo)
                        studio_posters.setdefault(key, []).append(film)

    # Fallback: check cached person_metadata table for any top person still missing a portrait.
    top_person_ids = [
        p["id"]
        for p in (stats.get("top_directors") or []) + (stats.get("top_actors") or [])
        if p.get("id") and str(p["id"]) not in person_portraits
    ]
    if top_person_ids:
        try:
            meta_rows = db.query(
                "SELECT person_id, data_json FROM person_metadata WHERE person_id IN ("
                + ",".join("?" for _ in top_person_ids)
                + ")",
                *top_person_ids,
            )
            for mrow in meta_rows:
                try:
                    pdata = json.loads(mrow["data_json"] or "{}")
                except (TypeError, ValueError):
                    continue
                profile_path = pdata.get("profile_path")
                if isinstance(profile_path, str) and profile_path.startswith("/"):
                    person_portraits[str(mrow["person_id"])] = (
                        f"https://image.tmdb.org/t/p/w185{profile_path}"
                    )
        except Exception:
            pass

    def sort_films(items):
        items.sort(
            key=lambda f: (
                -(f["rating"] or 0),
                -(1 if f["favorite"] else 0),
                -(f["year"] or 0),
                f["title"].casefold(),
            )
        )
        return items

    for bucket in (by_date, by_month, by_weekday, by_rating, by_genre, by_decade, by_runtime):
        for items in bucket.values():
            sort_films(items)

    heatmap_titles = {}
    for iso_d, items in by_date.items():
        titles = [f["title"] for f in items[:3]]
        suffix = f" +{len(items) - 3}" if len(items) > 3 else ""
        heatmap_titles[iso_d] = ", ".join(titles) + suffix

    decade_posters = {}
    for dec_key, items in by_decade.items():
        posters = [
            {"poster_path": f["poster_path"], "title": f["title"]}
            for f in items
            if f.get("poster_path")
        ][:3]
        decade_posters[dec_key] = posters

    def resolve_person_visual(person):
        pid = str(person["id"]) if person.get("id") else None
        name_k = _text(person.get("name")).casefold()
        portrait = (
            person_portraits.get(pid) if pid else None
        ) or person_portraits.get(name_k)
        return {"portrait_url": portrait, "monogram": _monogram(person.get("name"))}

    director_visuals = {
        (str(p["id"]) if p.get("id") else p["name"].casefold()): resolve_person_visual(p)
        for p in (stats.get("top_directors") or [])
    }
    actor_visuals = {
        (str(p["id"]) if p.get("id") else p["name"].casefold()): resolve_person_visual(p)
        for p in (stats.get("top_actors") or [])
    }

    studio_visuals = {}
    for studio in stats.get("top_studios") or []:
        sid = str(studio["id"]) if studio.get("id") else None
        sname_k = _text(studio.get("name")).casefold()
        lookup_key = sid or sname_k
        films = list(
            {
                f["id"]: f
                for f in (
                    (studio_posters.get(sid) or [])
                    + (studio_posters.get(sname_k) or [])
                )
            }.values()
        )
        sort_films(films)
        studio_visuals[lookup_key] = {
            "logo_url": (studio_logos.get(sid) if sid else None)
            or studio_logos.get(sname_k),
            "monogram": _monogram(studio.get("name")),
            "posters": [
                {"poster_path": f["poster_path"], "title": f["title"]}
                for f in films
                if f.get("poster_path")
            ][:3],
        }

    rated_total = stats["totals"].get("rated") or 0
    rating_dist = stats.get("rating_distribution") or []
    rating_peak = max((item["count"] for item in rating_dist), default=0)
    rating_ladder = [
        {
            "rating": item["rating"],
            "count": item["count"],
            "bar_width": _scale(item["count"], rating_peak, minimum=6),
            "share_pct": round(item["count"] * 100 / rated_total) if rated_total else 0,
        }
        for item in reversed(rating_dist)
    ]

    return {
        "drilldown": {
            "by_date": by_date,
            "by_month": by_month,
            "by_weekday": by_weekday,
            "by_rating": by_rating,
            "by_genre": by_genre,
            "by_decade": by_decade,
            "by_runtime": by_runtime,
        },
        "heatmap_titles": heatmap_titles,
        "decade_posters": decade_posters,
        "director_visuals": director_visuals,
        "actor_visuals": actor_visuals,
        "studio_visuals": studio_visuals,
        "monthly_wave": _build_monthly_wave(stats.get("monthly_activity") or []),
        "rating_ladder": rating_ladder,
    }
