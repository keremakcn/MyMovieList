"""Disposable UI fixture. Real AppData and provider requests are never used."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app
from test_recommendations import mock_recommendations
from werkzeug.serving import make_server


def main():
    with TemporaryDirectory(prefix="recommendation-preview-") as folder_name:
        folder = Path(folder_name)
        app = create_app(
            dict(
                TESTING=True,
                SECRET_KEY="isolated-preview",
                DATA_DIR=str(folder),
                DATABASE=str(folder / "library.db"),
                UI_LANGUAGE_DETECTOR=lambda: "en",
            )
        )
        for i in range(1, 20):
            app.extensions["db"].add_tmdb(
                dict(
                    tmdb_id=900000 + i,
                    title=f"Rated film {i}",
                    genre="Thriller" if i % 3 else "Comedy",
                    rating=9,
                    status="Watched",
                    note="Private test note",
                )
            )
        mock_recommendations(app)
        get = app.extensions["tmdb"].get

        def delayed(path, **params):
            time.sleep(0.025)
            return get(path, **params)

        app.extensions["tmdb"].get = delayed
        print("Disposable recommendation preview: http://127.0.0.1:62941", flush=True)
        make_server("127.0.0.1", 62941, app, threaded=True).serve_forever()


if __name__ == "__main__":
    main()
