"""Provider-neutral personal records. Public catalog metadata never enters sync."""

import json
import re
from datetime import date, datetime, timezone
from uuid import UUID

FIELDS = frozenset(
    (
        "status",
        "rating",
        "note",
        "favorite",
        "watched_date",
        "added_at",
        "order_key",
        "deleted_at",
        "custom",
    )
)
KEY = re.compile(
    r"^(tmdb:[1-9][0-9]{0,9}|custom:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$"
)
ORDER = re.compile(
    r"^[0-9]{20}:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def timestamp(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("A record timestamp must include a timezone.")
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds")


def validate_record(key, data):
    if not isinstance(key, str) or not KEY.fullmatch(key):
        raise ValueError("Invalid movie identity.")
    if not isinstance(data, dict) or set(data) != FIELDS:
        raise ValueError("Unexpected personal record fields.")
    data = dict(data)
    if (
        data["status"] not in ("Watchlist", "Watched")
        or type(data["favorite"]) is not bool
    ):
        raise ValueError("Invalid status or favorite.")
    if data["rating"] is not None and (
        type(data["rating"]) is not int or not 1 <= data["rating"] <= 10
    ):
        raise ValueError("Rating must be between 1 and 10.")
    if data["note"] is not None and (
        not isinstance(data["note"], str) or len(data["note"]) > 20000
    ):
        raise ValueError("Keep notes under 20,000 characters.")
    if data["watched_date"] is not None:
        if not isinstance(data["watched_date"], str) or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}", data["watched_date"]
        ):
            raise ValueError("Enter a valid watched date.")
        date.fromisoformat(data["watched_date"])
    data["added_at"] = timestamp(data["added_at"])
    if data["deleted_at"] is not None:
        data["deleted_at"] = timestamp(data["deleted_at"])
    if not isinstance(data["order_key"], str) or not ORDER.fullmatch(data["order_key"]):
        raise ValueError("Invalid original library order.")
    UUID(data["order_key"][21:])
    custom = data["custom"]
    if key.startswith("tmdb:"):
        if custom is not None:
            raise ValueError("Catalog metadata is not stored in the cloud.")
    else:
        if not isinstance(custom, dict) or set(custom) != {"title", "year", "genre"}:
            raise ValueError("Invalid custom film fields.")
        if (
            not isinstance(custom["title"], str)
            or not 1 <= len(custom["title"].strip()) <= 300
        ):
            raise ValueError("Enter a title of 1–300 characters.")
        if custom["year"] is not None and (
            type(custom["year"]) is not int or not 1800 <= custom["year"] <= 2200
        ):
            raise ValueError("Enter a valid release year.")
        if custom["genre"] is not None and (
            not isinstance(custom["genre"], str) or len(custom["genre"]) > 300
        ):
            raise ValueError("Invalid custom film genre.")
    return data


def from_movie(row):
    # An unknown legacy date stays unknown locally. A separate stable fallback
    # allows a portable record without rewriting the user's original metadata.
    original = datetime.fromisoformat(
        (row.get("sync_added_at") or row["created_at"]).replace("Z", "+00:00")
    )
    if original.tzinfo is None:
        original = original.replace(tzinfo=timezone.utc)
    return validate_record(
        row["record_key"],
        {
            "status": row["status"],
            "rating": row["rating"],
            "note": row["note"],
            "favorite": bool(row["favorite"]),
            "watched_date": row["watched_date"],
            "added_at": original.isoformat(),
            "order_key": row["order_key"],
            "deleted_at": row["deleted_at"],
            "custom": None
            if row["tmdb_id"]
            else {k: row[k] for k in ("title", "year", "genre")},
        },
    )


def three_way(base, local, remote):
    """Independent fields merge; competing notes/deletion never silently win."""
    if base is None:
        personal = FIELDS - {"added_at", "order_key"}
        return (
            (dict(remote), False)
            if all(local[k] == remote[k] for k in personal)
            else (None, True)
        )
    ours = {k for k in FIELDS if local[k] != base[k]}
    theirs = {k for k in FIELDS if remote[k] != base[k]}
    if any(local[k] != remote[k] for k in ours & theirs):
        return None, True
    edits = FIELDS - {"deleted_at", "added_at", "order_key"}
    if ("deleted_at" in ours and theirs & edits) or (
        "deleted_at" in theirs and ours & edits
    ):
        return None, True
    merged = {k: local[k] if k in ours else remote[k] for k in FIELDS}
    for k in ("added_at", "order_key"):
        merged[k] = remote[k]
    return merged, False
