"""Bounded TMDB cache and single-flight requests shared by all discovery views."""

import hashlib
import json
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from collections import OrderedDict
from concurrent.futures import Future
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class TMDBError(Exception):
    def __init__(self, message, status=502, retry_after=3):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


class TMDBClient:
    def __init__(self, token_provider, capacity=256):
        self.token_provider = token_provider
        self.capacity = capacity
        self.cache = OrderedDict()
        self.pending = {}
        self.lock = Lock()
        self.cooldown = {}

    def invalidate(self, path):
        with self.lock:
            for key in list(self.cache):
                if key[1] == path:
                    del self.cache[key]

    def get(self, path, **params):
        token = self.token_provider()
        if not token:
            raise TMDBError("Add your TMDB token in Settings to explore movies.", 503)
        key = (
            hashlib.sha256(token.encode()).hexdigest(),
            path,
            urlencode(sorted(params.items())),
        )
        with self.lock:
            cached = self.cache.get(key)
            if cached and cached[0] > time.monotonic():
                self.cache.move_to_end(key)
                if isinstance(cached[1], TMDBError):
                    raise cached[1]
                return cached[1]
            if self.cooldown.get(key[0], 0) > time.monotonic():
                raise TMDBError(
                    "TMDB is busy. Please wait a moment and try again.", 429
                )
            future = self.pending.get(key)
            owner = future is None
            if owner:
                future = self.pending[key] = Future()
        if not owner:
            return future.result(timeout=15)
        try:
            result = self._request(path, params, token)
            ttl = 120 if path.startswith("search/") else 21600
        except TMDBError as error:
            result, ttl = error, error.retry_after
        except Exception:
            result, ttl = (
                TMDBError("TMDB returned an unexpected response. Please try again."),
                3,
            )
        with self.lock:
            if isinstance(result, TMDBError) and result.status == 429:
                self.cooldown[key[0]] = time.monotonic() + ttl
            self.cache[key] = (time.monotonic() + ttl, result)
            self.cache.move_to_end(key)
            while len(self.cache) > self.capacity:
                self.cache.popitem(last=False)
            self.pending.pop(key, None)
            if isinstance(result, TMDBError):
                future.set_exception(result)
            else:
                future.set_result(result)
        if isinstance(result, TMDBError):
            raise result
        return result

    def _request(self, path, params, token):
        req = Request(
            "https://api.themoviedb.org/3/" + path + "?" + urlencode(params),
            headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
        )
        try:
            with urlopen(req, timeout=8) as response:
                data = json.load(response)
            if not isinstance(data, dict):
                raise ValueError("Expected an object")
            return data
        except HTTPError as error:
            if error.code in (401, 403):
                raise TMDBError(
                    "TMDB rejected the token. Check your token in Settings.", 503
                ) from error
            if error.code == 429:
                retry = error.headers.get("Retry-After", "10")
                try:
                    delay = max(1, int(retry))
                except ValueError:
                    try:
                        delay = max(
                            1,
                            (
                                parsedate_to_datetime(retry)
                                - datetime.now(timezone.utc)
                            ).total_seconds(),
                        )
                    except (ValueError, TypeError):
                        delay = 10
                raise TMDBError(
                    "TMDB is busy. Please wait a moment and try again.", 429, delay
                ) from error
            if error.code == 404:
                raise TMDBError(
                    "This item is no longer available on TMDB.", 404
                ) from error
            raise TMDBError(
                "TMDB is temporarily unavailable. Please try again."
            ) from error
        except (URLError, TimeoutError, OSError, ValueError) as error:
            raise TMDBError(
                "Could not reach TMDB. Check your connection and try again."
            ) from error


def image_url(path, size="w342"):
    return (
        f"https://image.tmdb.org/t/p/{size}{path}"
        if path and path.startswith("/")
        else None
    )


def movie_summary(data):
    release = data.get("release_date") or ""
    return {
        "tmdb_id": data["id"],
        "title": data.get("title") or "Untitled movie",
        "year": int(release[:4]) if release[:4].isdigit() else None,
        "poster_url": image_url(data.get("poster_path")),
        "overview": data.get("overview") or "",
        "score_percent": round((data.get("vote_average") or 0) * 10)
        if data.get("vote_count")
        else None,
    }


def movie_details(data):
    result = movie_summary(data)
    credits = data.get("credits") or {}
    people = [
        {
            "id": p["id"],
            "name": p["name"],
            "role": p.get("character") or p.get("job") or "",
        }
        for p in credits.get("cast", [])[:12]
    ]

    def crew_members(jobs):
        members = {}
        for person in credits.get("crew", []):
            job = person.get("job")
            if job not in jobs:
                continue
            member = members.setdefault(
                person["id"], {"id": person["id"], "name": person["name"], "roles": []}
            )
            if job not in member["roles"]:
                member["roles"].append(job)
        return [
            dict(id=p["id"], name=p["name"], role=", ".join(p["roles"]))
            for p in members.values()
        ]

    directors = crew_members({"Director"})
    writers = crew_members(
        {"Writer", "Screenplay", "Story", "Novel", "Characters", "Adaptation"}
    )
    producers = crew_members(
        {"Producer", "Executive Producer", "Co-Producer", "Associate Producer"}
    )
    companies = [
        {"id": c["id"], "name": c["name"]} for c in data.get("production_companies", [])
    ]
    result.update(
        genre=", ".join(g["name"] for g in data.get("genres", [])),
        runtime=data.get("runtime"),
        director=", ".join(p["name"] for p in directors),
        cast=[p["name"] for p in people],
        entities={
            "cast": people,
            "directors": directors,
            "writers": writers,
            "producers": producers,
            "companies": companies,
        },
    )
    return result
