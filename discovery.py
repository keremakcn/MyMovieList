"""Public movie collections with fresh, device-local library membership."""

from datetime import date, timedelta
from math import isfinite

from tmdb_client import TMDBError, movie_summary

COLLECTIONS = {
    "trending": {
        "key": "trending",
        "title": "Trending films",
        "description": "The films getting people talking right now.",
    },
    "top-rated": {
        "key": "top-rated",
        "title": "Highest rated",
        "description": "Great films that have stood the test of many ratings.",
    },
    "new-releases": {
        "key": "new-releases",
        "title": "New releases",
        "description": "Discover films released in the last 90 days.",
    },
    "genres": {
        "key": "genres",
        "title": "Explore by genre",
        "description": "Choose a genre and follow your curiosity.",
    },
}

# Public TMDB movie genre IDs. A genre chooser should work without a network call.
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


def valid_movies(items):
    """Return fresh summaries without modifying provider data shared by the cache."""
    seen, movies = set(), []
    if not isinstance(items, list):
        raise TMDBError("Movie discovery returned an unexpected response. Please try again.")
    for item in items:
        if not isinstance(item, dict):
            continue
        movie_id = item.get("id")
        if (
            type(movie_id) is not int
            or not 1 <= movie_id <= 9_999_999_999
            or movie_id in seen
            or item.get("adult")
            or item.get("video")
        ):
            continue
        raw = dict(item)
        for name in ("title", "overview", "release_date", "poster_path"):
            if not isinstance(raw.get(name), str):
                raw[name] = ""
        score = raw.get("vote_average")
        votes = raw.get("vote_count")
        if (
            type(score) not in (int, float)
            or not 0 <= score <= 10
            or not isfinite(score)
            or type(votes) is not int
            or votes <= 0
        ):
            raw["vote_count"] = 0
        movies.append(movie_summary(raw))
        seen.add(movie_id)
        if len(movies) == 20:
            break
    return movies


def provider_count(value, default=0, maximum=None):
    if type(value) is not int or value < 0:
        return default
    return min(value, maximum) if maximum is not None else value


class DiscoveryService:
    def __init__(self, tmdb, db, today=None):
        self.tmdb = tmdb
        self.db = db
        self.today = today or date.today

    def feed(self, collection, *, page=1, window="week", genre=None,
             hide_library=False, limit=20, language="en-US"):
        if collection not in COLLECTIONS:
            raise ValueError("Choose a valid movie collection.")
        if type(page) is not int or not 1 <= page <= 500:
            raise ValueError("Choose a page between 1 and 500.")
        if window not in ("day", "week"):
            raise ValueError("Choose daily or weekly trends.")
        if genre is not None and (type(genre) is not int or genre not in GENRES):
            raise ValueError("Choose a valid movie genre.")
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("Choose between 1 and 20 films.")

        context = {
            "collection": collection, "collection_info": COLLECTIONS[collection],
            "title": COLLECTIONS[collection]["title"],
            "description": COLLECTIONS[collection]["description"],
            "genre": genre, "genres": GENRES, "window": window, "hide_library": hide_library,
            "movies": [], "page": page, "pages": 0, "total": 0, "total_provider": 0,
            "visible_count": 0, "hidden_count": 0, "error": None,
        }
        if collection == "genres" and genre is None:
            return context

        params = {"language": language, "page": page}
        if collection == "trending":
            path = f"trending/movie/{window}"
        elif collection == "top-rated":
            path = "movie/top_rated"
        else:
            path = "discover/movie"
            params.update(include_adult="false", include_video="false",
                          sort_by="popularity.desc")
            today = self.today()
            params["primary_release_date.lte"] = today.isoformat()
            if collection == "new-releases":
                params["primary_release_date.gte"] = (
                    today - timedelta(days=90)
                ).isoformat()
            else:
                params["with_genres"] = genre

        data = self.tmdb.get(path, **params)
        if not isinstance(data, dict):
            raise TMDBError("Movie discovery returned an unexpected response. Please try again.")
        movies = valid_movies(data.get("results", []))
        membership = self.db.membership([movie["tmdb_id"] for movie in movies])
        for movie in movies:
            movie["library"] = membership.get(movie["tmdb_id"])
        context["hidden_count"] = (
            sum(movie["library"] is not None for movie in movies) if hide_library else 0
        )
        if hide_library:
            movies = [movie for movie in movies if movie["library"] is None]
        movies = movies[:limit]
        total = provider_count(data.get("total_results"))
        context.update(
            movies=movies, visible_count=len(movies), total=total,
            total_provider=total,
            pages=provider_count(data.get("total_pages"), maximum=500),
        )
        return context
