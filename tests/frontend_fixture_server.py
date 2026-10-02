"""Isolated UI fixture server. Never opens or modifies the user's live library."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import create_app  # noqa: E402
from test_app import MOVIE  # noqa: E402
from test_recommendations import mock_recommendations  # noqa: E402
from waitress import serve  # noqa: E402

data = ROOT / '.qa' / 'frontend-fixture'
data.mkdir(parents=True, exist_ok=True)
app = create_app({'DATA_DIR': str(ROOT), 'DATABASE': str(data / 'movies.db'), 'SECRET_KEY': 'isolated-frontend-test'})
mock_recommendations(app)
original_get = app.extensions['tmdb'].get
films = [
    (497, 'The Green Mile', 1999, 'Fantasy, Drama, Crime', 9, 'Watched'),
    (238, 'The Godfather', 1972, 'Drama, Crime', 10, 'Watched'),
    (24, 'Kill Bill: Vol. 1', 2003, 'Action, Crime', 9, 'Watched'),
    (393, 'Kill Bill: Vol. 2', 2004, 'Action, Thriller', None, 'Watchlist'),
    (242, 'The Godfather Part III', 1990, 'Drama, Crime', None, 'Watchlist'),
    (1576132, 'A very long film title that should never move the actions or expand the card', 2025, 'Drama', 7, 'Watched'),
]
db = app.extensions['db']
for mid, title, year, genre, rating, status in films:
    db.add_tmdb(dict(tmdb_id=mid, title=title, year=year, genre=genre, rating=rating,
                    status=status, favorite=int(rating == 10), poster_path=f'/posters/{mid}.jpg',
                    score_percent=85, note='Some stories stay with you long after the credits.\nA second line that belongs on the detail page.'))
db.add_tmdb(dict(tmdb_id=900000, title='A film without a poster', year=2020, genre='Drama', status='Watchlist'))

def fixture_get(path, **params):
    if path == 'search/person':
        return {'results': [{'id': 6384, 'name': 'Keanu Reeves', 'known_for_department': 'Acting', 'known_for': []}], 'total_pages': 1}
    if path == 'search/company':
        return {'results': [{'id': 174, 'name': 'Warner Bros.'}], 'total_pages': 1}
    if path.startswith('person/'):
        return {'id': 6384, 'name': 'Keanu Reeves', 'known_for_department': 'Acting', 'biography': 'Explore a career through the films that made it.', 'movie_credits': {'cast': [MOVIE], 'crew': []}}
    if path.startswith('company/'):
        return {'id': 174, 'name': 'Warner Bros.', 'description': 'Discover the films from this studio.'}
    if path == 'discover/movie' and 'with_companies' in params:
        return {'results': [MOVIE], 'total_pages': 1}
    return original_get(path, **params)

app.extensions['tmdb'].get = fixture_get
if __name__ == '__main__':
    serve(app, host='127.0.0.1', port=int(os.environ.get('PREVIEW_TEST_PORT', '5057')))
