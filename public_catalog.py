"""Resolve public film selections using this device's catalog and library only."""

from concurrent.futures import ThreadPoolExecutor

from tmdb_client import TMDBError


def present_public_movies(library, picks, locale):
    ids = list(dict.fromkeys(pick["tmdb_id"] for pick in picks))
    owned = (
        {
            row["tmdb_id"]: row
            for row in library.db.query(
                "SELECT * FROM movies WHERE deleted_at IS NULL AND tmdb_id IN ("
                + ",".join("?" for _ in ids)
                + ")",
                *ids,
            )
        }
        if ids
        else {}
    )

    def load(mid):
        try:
            details = library.catalog.details(mid)
        except (TMDBError, ValueError, TypeError):
            details = {
                "tmdb_id": mid,
                "title": "#" + str(mid),
                "overview": "",
                "year": None,
                "poster_url": None,
                "score_percent": None,
            }
        return dict(details, library=owned.get(mid))

    with ThreadPoolExecutor(max_workers=3) as executor:
        movies = list(executor.map(load, ids))
    return {
        movie["tmdb_id"]: movie for movie in library.catalog.present(movies, locale)
    }
