"""Strict, bounded public projections for in-app member discovery."""

import base64
import json
from datetime import date, timedelta

from account_profile import AVATAR_IDS, validate_profile
from account_username import normalize_username

PAGE_LIMITS = {"people": 16, "week": 12}


def normalize_query(value):
    if not isinstance(value, str):
        raise ValueError("Enter a valid member search.")  # noqa: TRY004 — one validation contract
    value = value.strip().removeprefix("@")
    if len(value) > 60 or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("Keep member searches under 60 characters.")
    return value


def validate_person(value):
    if not isinstance(value, dict) or set(value) != {
        "username",
        "display_name",
        "avatar_id",
    }:
        raise ValueError("Invalid public member.")
    if (
        normalize_username(value["username"]) != value["username"]
        or not isinstance(value["avatar_id"], str)
        or value["avatar_id"] not in AVATAR_IDS
    ):
        raise ValueError("Invalid public member.")
    validate_profile({key: value[key] for key in ("display_name", "avatar_id")})
    return dict(value)


def iso_date(value):
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError("Invalid public date.")
    day = date.fromisoformat(value)
    if day.isoformat() != value:
        raise ValueError("Invalid public date.")
    return day


def validate_position(view, value):
    if value is None:
        return None
    fields = (
        {"username"}
        if view == "people"
        else {"username", "tmdb_id", "watched_date", "week_start"}
    )
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("Invalid social cursor.")
    if normalize_username(value["username"]) != value["username"]:
        raise ValueError("Invalid social cursor.")
    if view == "week":
        if (
            type(value["tmdb_id"]) is not int
            or not 1 <= value["tmdb_id"] <= 9_999_999_999
        ):
            raise ValueError("Invalid social cursor.")
        iso_date(value["watched_date"])
        iso_date(value["week_start"])
    return dict(value)


def encode_cursor(view, query, position):
    raw = json.dumps(
        {"view": view, "query": query, "position": position},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(token, view, query):
    if not token:
        return None
    if not isinstance(token, str) or len(token) > 1024:
        raise ValueError("Invalid social cursor.")
    try:
        raw = base64.b64decode(
            token + "=" * (-len(token) % 4), altchars=b"-_", validate=True
        )
        value = json.loads(raw)
        if (
            not isinstance(value, dict)
            or set(value) != {"view", "query", "position"}
            or value["view"] != view
            or value["query"] != query
        ):
            raise ValueError("Invalid social cursor.")
        return validate_position(view, value["position"])
    except (ValueError, TypeError, UnicodeError, KeyError) as error:
        raise ValueError("Invalid social cursor.") from error


def validate_page(value, view):
    if (
        view not in PAGE_LIMITS
        or not isinstance(value, dict)
        or set(value)
        != {"protocol", "view", "rows", "next_cursor", "week_start", "week_end"}
        or type(value["protocol"]) is not int
        or value["protocol"] != 1
        or value["view"] != view
    ):
        raise ValueError("Invalid social response.")
    start, end = iso_date(value["week_start"]), iso_date(value["week_end"])
    if start.weekday() != 0 or end != start + timedelta(days=6):
        raise ValueError("Invalid social week.")
    if not isinstance(value["rows"], list) or len(value["rows"]) > PAGE_LIMITS[view]:
        raise ValueError("Invalid social page size.")
    rows, order, identities = [], [], set()
    for raw in value["rows"]:
        if view == "people":
            row = validate_person(raw)
            key = row["username"]
        else:
            fields = {
                "username",
                "display_name",
                "avatar_id",
                "tmdb_id",
                "watched_date",
            }
            if not isinstance(raw, dict) or set(raw) not in (
                fields,
                fields | {"rating"},
            ):
                raise ValueError("Invalid social activity.")
            validate_person(
                {key: raw[key] for key in ("username", "display_name", "avatar_id")}
            )
            if (
                type(raw["tmdb_id"]) is not int
                or not 1 <= raw["tmdb_id"] <= 9_999_999_999
                or not start <= iso_date(raw["watched_date"]) <= end
            ):
                raise ValueError("Invalid social activity.")
            if "rating" in raw and (
                type(raw["rating"]) is not int or not 1 <= raw["rating"] <= 10
            ):
                raise ValueError("Invalid social rating.")
            row = dict(raw)
            identity = row["username"], row["tmdb_id"]
            if identity in identities:
                raise ValueError("Duplicate social activity.")
            identities.add(identity)
            key = (
                -iso_date(row["watched_date"]).toordinal(),
                row["username"],
                row["tmdb_id"],
            )
        rows.append(row)
        order.append(key)
    if order != sorted(set(order)):
        raise ValueError("Duplicate or unsorted social rows.")
    cursor = validate_position(view, value["next_cursor"])
    if cursor is not None:
        if not rows or len(rows) != PAGE_LIMITS[view]:
            raise ValueError("Invalid social pagination.")
        expected = {"username": rows[-1]["username"]}
        if view == "week":
            expected.update(
                tmdb_id=rows[-1]["tmdb_id"],
                watched_date=rows[-1]["watched_date"],
                week_start=value["week_start"],
            )
        if cursor != expected:
            raise ValueError("Invalid social pagination.")
    return dict(value, rows=rows, next_cursor=cursor)
