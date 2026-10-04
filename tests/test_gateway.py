import io
import json
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

import pytest

from storage import Database
from tmdb_client import GATEWAY_BASE_URL, TMDBClient, TMDBError


def test_gateway_requests_never_send_local_credentials(monkeypatch):
    monkeypatch.setenv('TMDB_ACCESS_TOKEN', 'legacy-secret')
    requests = []

    def respond(request, timeout):
        requests.append(request)
        assert timeout == 12
        return io.BytesIO(json.dumps({'results': []}).encode())

    with patch('tmdb_client.urlopen', side_effect=respond):
        client = TMDBClient()
        client.get('search/movie', query='Alien & Friends', page=1)
        client.get('search/movie', query='Alien & Friends', page=1)
    assert len(requests) == 1
    request = requests[0]
    assert request.full_url.startswith(GATEWAY_BASE_URL)
    assert parse_qs(urlsplit(request.full_url).query)['query'] == ['Alien & Friends']
    assert request.get_header('Authorization') is None
    assert request.get_header('Cookie') is None
    from version import APP_VERSION
    assert request.get_header('User-agent') == f'MyMovieList/{APP_VERSION}'
    assert 'legacy-secret' not in request.full_url


def test_gateway_failure_preserves_offline_library(app, client):
    db = app.extensions['db']
    db.add_tmdb(dict(tmdb_id=603, title='The Matrix', note='Keep my note', rating=9, favorite=1))
    before = db.query('SELECT * FROM movies')
    with patch('tmdb_client.urlopen', side_effect=URLError('offline')):
        response = client.get('/search?q=matrix&categories=movie')
    assert b'Check your connection' in response.data
    assert b'Keep my note' in client.get('/').data
    assert db.query('SELECT * FROM movies') == before


def test_cleanup_preserves_personal_data_and_other_settings(tmp_path):
    db = Database(tmp_path / 'library.db')
    db.migrate()
    db.add_tmdb(dict(tmdb_id=603, title='The Matrix', note='Keep', rating=9, favorite=1))
    db.execute("INSERT INTO settings VALUES('tmdb_token', 'legacy-private-value')")
    db.execute("INSERT INTO settings VALUES('recommendation_mode', 'balanced')")
    before = db.query('SELECT * FROM movies')
    db.migrate()
    assert not db.query("SELECT * FROM settings WHERE key='tmdb_token'")
    assert db.query("SELECT value FROM settings WHERE key='recommendation_mode'")[0]['value'] == 'balanced'
    assert db.query('SELECT * FROM movies') == before
    assert b'legacy-private-value' not in (tmp_path / 'library.db').read_bytes()


@pytest.mark.parametrize('status', [401, 403, 404, 429, 502, 503])
def test_gateway_http_errors_do_not_ask_for_token(status):
    error = HTTPError(GATEWAY_BASE_URL, status, 'error', {'Retry-After':'60'}, io.BytesIO(b'{}'))
    with patch('tmdb_client.urlopen', side_effect=error), pytest.raises(TMDBError) as exc:
        TMDBClient().get('movie/603')
    assert 'Settings' not in str(exc.value) and 'token' not in str(exc.value).lower()
    if status == 429:
        assert exc.value.status == 429 and exc.value.retry_after == 60


@pytest.mark.parametrize('path,params', [('../movie/1', {}), ('movie/1?api_key=x', {}), ('movie/1', {'api_key':'secret'})])
def test_invalid_requests_never_leave_app(path, params):
    with patch('tmdb_client.urlopen') as fetch, pytest.raises(TMDBError):
        TMDBClient().get(path, **params)
    fetch.assert_not_called()


def test_custom_gateway_uses_https_without_credentials(monkeypatch):
    monkeypatch.setenv('MOVIE_WATCHLIST_GATEWAY_URL', 'https://api.example.com')
    with patch('tmdb_client.urlopen', return_value=io.BytesIO(b'{"results":[]}')) as fetch:
        TMDBClient().get('search/movie', query='Alien')
    request = fetch.call_args.args[0]
    assert request.full_url == 'https://api.example.com/3/search/movie?query=Alien'
    assert request.get_header('Authorization') is None


@pytest.mark.parametrize('url', ['http://api.example.com', 'https://user:secret@api.example.com', 'https://api.example.com?api_key=x', 'https://api.example.com/other', 'https://api.example.com/#fragment'])
def test_invalid_gateway_configuration(url):
    with pytest.raises(ValueError):
        TMDBClient(base_url=url)
