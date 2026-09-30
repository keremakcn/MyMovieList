"""Compatibility notice for the retired MovieLens catalog importer.

Discovery now uses TMDB. Existing movie_catalog data is preserved.
"""

if __name__ == "__main__":
    raise SystemExit(
        "The legacy catalog importer has been retired. Use Explore to find and add movies. No data was changed."
    )
