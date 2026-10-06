"""Bilingual UI fixture: entirely temporary data, deterministic catalog and offline switch."""

import copy
import os
from pathlib import Path
import sys
import tempfile
import time

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from app import create_app  # noqa: E402
from flask import jsonify, request  # noqa: E402
from tmdb_client import TMDBError  # noqa: E402
from waitress import serve  # noqa: E402

folder = Path(tempfile.mkdtemp(prefix="mymovielist-bilingual-"))
app = create_app(dict(DATA_DIR=str(folder), DATABASE=str(folder / "fixture.db"),
                      SECRET_KEY="isolated-bilingual-fixture", UI_LANGUAGE_DETECTOR=lambda: "tr"))
state = {"offline": False, "calls": []}
raw = dict(id=83651, title="The Chaos Class", original_title="Hababam Sınıfı", original_language="tr",
           release_date="1975-04-01", poster_path=None, overview="Students challenge school rules.",
           runtime=87, vote_average=8.1, vote_count=200, adult=False, video=False,
           genre_ids=[35], genres=[{"id": 35, "name": "Comedy"}],
           credits={"cast": [{"id": 100 + i, "name": f"Actor {i}", "character": f"Student {i}"} for i in range(15)],
                    "crew": [{"id": 300, "name": "Ertem Eğilmez", "job": "Director"}]},
           production_companies=[{"id": 174, "name": "Arzu Film"}],
           translations={"id": 83651, "translations": [{"iso_639_1": "tr", "iso_3166_1": "TR",
                          "data": {"title": "Hababam Sınıfı", "overview": "Hababam Sınıfı'nın okul maceraları."}}]})
matrix = dict(copy.deepcopy(raw), id=603, title="The Matrix", original_title="The Matrix", original_language="en",
              overview="A simulated reality.", translations={"id": 603, "translations": [
              {"iso_639_1": "tr", "iso_3166_1": "TR", "data": {"title": "Matrix", "overview": "Simüle edilmiş bir gerçeklik."}}]})
app.extensions["db"].add_tmdb(dict(tmdb_id=83651, title="The Chaos Class", status="Watched", note="Kişisel yorumum.",
                                   rating=9, favorite=1, watched_date="2020-02-03"))


def get(path, **params):
    state["calls"].append((path, params))
    if state["offline"]:
        raise TMDBError("Could not reach movie discovery. Check your connection and try again. Your saved library is still available.")
    if path.startswith("movie/"):
        time.sleep(0.25)
        return copy.deepcopy(matrix if path == "movie/603" else raw)
    if path.startswith("person/"):
        return dict(id=int(path.split("/")[1]), name="Ertem Eğilmez", known_for_department="Directing",
                    biography="Director.", movie_credits={"cast": [], "crew": [raw]})
    if path.startswith("company/"):
        return dict(id=174, name="Arzu Film", description="Production studio.")
    if path == "search/person" or path == "search/company":
        return dict(results=[], total_pages=0, total_results=0)
    films = [copy.deepcopy(raw), copy.deepcopy(matrix)]
    if params.get("language") == "tr-TR":
        for film in films:
            film["title"] = film["original_title"]
            film["overview"] = film["translations"]["translations"][0]["data"]["overview"]
    return dict(results=films, total_pages=1, total_results=2, page=1)


app.extensions["tmdb"].get = get


@app.get("/__qa/state")
def qa_state():
    return jsonify(movies=app.extensions["db"].query("SELECT * FROM movies ORDER BY id"),
                   calls=state["calls"], offline=state["offline"])


@app.post("/__qa/provider")
def qa_provider():
    state["offline"] = request.form.get("offline") == "1"
    return jsonify(ok=True)


if __name__ == "__main__":
    port = int(os.environ.get("PREVIEW_TEST_PORT", "5065"))
    print(f"Isolated bilingual preview on port {port}", flush=True)
    serve(app, host="127.0.0.1", port=port)
