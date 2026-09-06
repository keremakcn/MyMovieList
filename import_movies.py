import csv
import re

from cs50 import SQL

db = SQL("sqlite:///movies.db")

db.execute("DROP TABLE IF EXISTS movie_catalog")

db.execute("""
    CREATE TABLE movie_catalog (
        id INTEGER PRIMARY KEY,
        title TEXT NOT NULL,
        year INTEGER,
        genre TEXT,
        tmdb_id INTEGER
    )
""")

tmdb_ids = {}

with open("ml-25m/links.csv", "r", encoding="utf-8") as file:
    reader = csv.DictReader(file)

    for link in reader:
        movie_id = int(link["movieId"])
        tmdb_id = link["tmdbId"]

        if tmdb_id:
            tmdb_ids[movie_id] = int(tmdb_id)

with open("ml-25m/movies.csv", "r", encoding="utf-8") as file:
    reader = csv.DictReader(file)

    for movie in reader:
        movie_id = int(movie["movieId"])
        title = movie["title"]
        genres = movie["genres"].replace("|", ", ")

        match = re.search(r"\((\d{4})\)\s*$", title)

        if match:
            year = int(match.group(1))
            title = title[: match.start()].strip()
        else:
            year = None

        db.execute(
            """
            INSERT INTO movie_catalog (id, title, year, genre, tmdb_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            movie_id,
            title,
            year,
            genres,
            tmdb_ids.get(movie_id),
        )

print("Movie catalog imported successfully.")
