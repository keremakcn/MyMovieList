"""Deterministic discovery UI fixture, with optional live provider preview.

Every run uses a new temporary library. Never opens AppData or a source library.
"""
import os
from pathlib import Path
import sys
import tempfile
import time

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from app import create_app  # noqa: E402
from tmdb_client import TMDBError  # noqa: E402
from waitress import serve  # noqa: E402

data_dir = Path(tempfile.mkdtemp(prefix='mymovielist-discovery-'))
app = create_app({'DATA_DIR': str(data_dir), 'DATABASE': str(data_dir / 'fixture.db'),
                  'SECRET_KEY': 'discovery-ui-fixture', 'TEMPLATES_AUTO_RELOAD': True,
                  'UI_LANGUAGE_DETECTOR': lambda: 'en'})

if os.environ.get('DISCOVERY_LIVE') != '1':
    films = [dict(id=603 + i, title=('A deliberately long film title to check that poster cards and actions remain aligned' if i == 2 else f'Fixture film {i + 1}'),
                  release_date='2026-09-15', adult=False, video=False, poster_path=None,
                  overview='A film used to test discovery without requesting remote data.',
                  vote_average=8.2, vote_count=500, genre_ids=[18]) for i in range(20)]
    app.extensions['db'].add_tmdb(dict(tmdb_id=603, title='Fixture film 1', status='Watched', rating=9, favorite=1, note='Keep this private note.'))
    app.extensions['db'].add_tmdb(dict(tmdb_id=604, title='Fixture film 2', status='Watchlist'))
    calls = {}

    def get(path, **params):
        calls[path] = calls.get(path, 0) + 1
        if os.environ.get('DISCOVERY_SCENARIO') == 'errors' and path in ('movie/top_rated', 'movie/607') and calls[path] == 1:
            raise TMDBError('Discovery is temporarily unavailable. Please try again.', 503)
        if path == 'trending/movie/day':
            time.sleep(0.7)
        if path == 'movie/top_rated' or path.startswith('trending/movie/') or path == 'discover/movie':
            page = int(params.get('page', 1))
            page_films = [dict(film, id=film['id'] + (page - 1) * 100) for film in films]
            if path.endswith('/day'):
                page_films = [dict(film, title='Daily ' + film['title']) for film in page_films]
            return dict(results=page_films, total_pages=3, total_results=60, page=page)
        if path == 'search/movie':
            return dict(results=films[:2], total_pages=1, total_results=2)
        if path.startswith('movie/') and path.split('/')[1].isdigit():
            mid = int(path.split('/')[1])
            return dict(films[(mid - 603) % 20], id=mid, runtime=120,
                        genres=[{'id': 18, 'name': 'Drama'}],
                        credits={'cast': [], 'crew': []}, production_companies=[])
        if path == 'search/person' or path == 'search/company':
            return dict(results=[], total_pages=0, total_results=0)
        raise AssertionError(f'Unexpected fixture provider path: {path}')

    app.extensions['tmdb'].get = get

if __name__ == '__main__':
    print(f'Isolated discovery preview on port {os.environ.get("PREVIEW_TEST_PORT", "5058")}', flush=True)
    serve(app, host='127.0.0.1', port=int(os.environ.get('PREVIEW_TEST_PORT', '5058')))
