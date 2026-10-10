"""Portable per-field edit times; no public catalog fields participate in sync."""

import json
from datetime import datetime, timedelta, timezone

from personal_data import FIELDS, three_way, timestamp

EDITABLE = FIELDS - {"added_at", "order_key"}


def validate_versions(value):
    if not isinstance(value, dict) or not set(value) <= EDITABLE:
        raise ValueError("Invalid field edit times.")
    return {key: timestamp(when) for key, when in value.items()}


def clock_now(con):
    def setting(key, default):
        row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    current = datetime.now(timezone.utc) + timedelta(
        seconds=float(setting("sync_clock_offset", "0"))
    )
    previous = setting("sync_clock_last", "")
    if previous:
        previous = datetime.fromisoformat(previous)
        # A backwards clock does not turn a later local edit into an older edit.
        # An implausible old high-water mark is not allowed to poison future edits.
        if previous <= current + timedelta(minutes=5):
            current = max(current, previous + timedelta(microseconds=1))
    value = current.isoformat(timespec="microseconds")
    con.execute(
        "INSERT OR REPLACE INTO settings VALUES ('sync_clock_last',?)", (value,)
    )
    return value


def observe(con, versions):
    versions = validate_versions(versions)
    current = datetime.now(timezone.utc)
    offset = con.execute(
        "SELECT value FROM settings WHERE key='sync_clock_offset'"
    ).fetchone()
    if offset:
        current += timedelta(seconds=float(offset[0]))
    plausible = [
        v
        for v in versions.values()
        if datetime.fromisoformat(v) <= current + timedelta(minutes=5)
    ]
    if not plausible:
        return
    old = con.execute(
        "SELECT value FROM settings WHERE key='sync_clock_last'"
    ).fetchone()
    value = max(plausible + ([old[0]] if old else []))
    con.execute(
        "INSERT OR REPLACE INTO settings VALUES ('sync_clock_last',?)", (value,)
    )


def state(con, key):
    row = con.execute(
        "SELECT versions_json FROM sync_field_state WHERE record_key=?", (key,)
    ).fetchone()
    return json.loads(row[0]) if row else {}


def save_state(con, key, data, versions):
    from personal_data import dumps

    con.execute(
        "INSERT OR REPLACE INTO sync_field_state VALUES (?,?,?)",
        (key, dumps(data), dumps(validate_versions(versions))),
    )
    observe(con, versions)


def merge(base, local, remote, local_versions, remote_versions, *, now=None):
    """Merge independent edits, then resolve competing values by actual edit time.

    Missing, equal or implausibly future times retain the recoverable review path.
    The cloud revision still controls atomic writes and incremental downloads.
    """
    ours = validate_versions(local_versions)
    theirs = validate_versions(remote_versions)
    now = datetime.fromisoformat(timestamp(now)) if now else datetime.now(timezone.utc)
    limit = now + timedelta(minutes=5)

    def newer(key):
        left, right = ours.get(key), theirs.get(key)
        if not left or not right or left == right:
            return None
        if any(datetime.fromisoformat(t) > limit for t in (left, right)):
            return None
        return left > right

    changed_local = (
        EDITABLE if base is None else {k for k in EDITABLE if local[k] != base[k]}
    )
    changed_remote = (
        EDITABLE if base is None else {k for k in EDITABLE if remote[k] != base[k]}
    )
    result, versions = dict(remote), dict(theirs)
    for key in EDITABLE:
        if key in changed_local:
            if key in changed_remote and local[key] != remote[key]:
                keep_local = newer(key)
                if keep_local is None:
                    return None, {}, True
            else:
                keep_local = True
            if keep_local:
                result[key] = local[key]
                if key in ours:
                    versions[key] = ours[key]
                else:
                    versions.pop(key, None)
        if local[key] == remote[key] and key in ours and key in theirs:
            versions[key] = max(ours[key], theirs[key])

    # A newer edit can restore an older deletion; a newer deletion wins over an
    # older offline edit. Keep the merged personal values behind the tombstone.
    for deleted, edited, deleted_versions, edited_versions, changed in (
        (local, remote, ours, theirs, changed_remote),
        (remote, local, theirs, ours, changed_local),
    ):
        if deleted["deleted_at"] is None or edited["deleted_at"] is not None:
            continue
        edits = changed - {"deleted_at"}
        if not edits or (
            base is not None and deleted["deleted_at"] == base["deleted_at"]
        ):
            continue
        deletion = deleted_versions.get("deleted_at")
        edit_times = [edited_versions.get(k) for k in edits]
        if not deletion or any(t is None for t in edit_times):
            return None, {}, True
        if any(datetime.fromisoformat(t) > limit for t in [deletion, *edit_times]):
            return None, {}, True
        newest = max(edit_times)
        if newest == deletion:
            return None, {}, True
        result["deleted_at"] = None if newest > deletion else deleted["deleted_at"]
        versions["deleted_at"] = max(newest, deletion)
    result["added_at"], result["order_key"] = remote["added_at"], remote["order_key"]
    return result, versions, False


def legacy_merge(base, local, remote):
    return three_way(base, local, remote)
