import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

from api.google_auth import verify_google_access_token


def _mock_response(body):
    mock = MagicMock()
    mock.read.return_value = body
    mock.__enter__.return_value = mock
    mock.__exit__.return_value = False
    return mock


def test_verify_google_access_token_merges_tokeninfo_aud_with_userinfo_profile():
    tokeninfo = _mock_response(b'{"aud": "client-1", "scope": "openid email"}')
    userinfo = _mock_response(
        b'{"sub": "sub-1", "email": "ada@example.com", "email_verified": true, '
        b'"hd": "example.com"}'
    )

    with patch.object(urllib.request, 'urlopen', side_effect=[tokeninfo, userinfo]):
        claims = verify_google_access_token('a-token')

    assert claims == {
        'sub': 'sub-1',
        'email': 'ada@example.com',
        'email_verified': True,
        'hd': 'example.com',
        'aud': 'client-1',
    }


def test_verify_google_access_token_returns_none_when_tokeninfo_rejects_the_token():
    with patch.object(
        urllib.request,
        'urlopen',
        side_effect=urllib.error.HTTPError('url', 400, 'Bad Request', {}, None),
    ):
        assert verify_google_access_token('a-token') is None


def test_verify_google_access_token_returns_none_when_userinfo_rejects_the_token():
    tokeninfo = _mock_response(b'{"aud": "client-1"}')

    with patch.object(
        urllib.request,
        'urlopen',
        side_effect=[tokeninfo, urllib.error.HTTPError('url', 401, 'Unauthorized', {}, None)],
    ):
        assert verify_google_access_token('a-token') is None


def test_verify_google_access_token_returns_none_on_malformed_json():
    tokeninfo = _mock_response(b'not json')

    with patch.object(urllib.request, 'urlopen', return_value=tokeninfo):
        assert verify_google_access_token('a-token') is None


def test_verify_google_access_token_returns_none_on_network_error():
    with patch.object(urllib.request, 'urlopen', side_effect=urllib.error.URLError('no route')):
        assert verify_google_access_token('a-token') is None
