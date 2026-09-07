import http.client
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

TOKENINFO_URL = 'https://oauth2.googleapis.com/tokeninfo'
USERINFO_URL = 'https://openidconnect.googleapis.com/v1/userinfo'


def _get_json(url, headers=None):
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read()
    except (urllib.error.URLError, http.client.HTTPException, OSError):
        logger.warning('Google verification request to %s failed.', url, exc_info=True)
        return None
    try:
        return json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.warning('Google verification response from %s was not valid JSON.', url, exc_info=True)
        return None


def verify_google_access_token(access_token):
    """Verify `access_token` with Google and return its claims, or None if unusable.

    Two calls, each read only for the claim(s) Google actually documents on it: tokeninfo
    for `aud` (what client the opaque access token was issued to - userinfo cannot answer
    this), userinfo for `sub`/`email`/`email_verified`/`hd` (Google's documented,
    production-supported source for profile claims from an access token - tokeninfo's
    access-token variant is not confirmed to carry `hd`). See design.md.

    Deliberately broad: a non-2xx response, a network failure, or a malformed body from
    either call all mean the same thing to the caller - this token cannot be trusted - so
    none of them is allowed to escape as anything other than None. Mirrors
    try_deliver_reset_link's "nothing here reaches the caller as a 500" shape.
    """
    tokeninfo_url = f'{TOKENINFO_URL}?{urllib.parse.urlencode({"access_token": access_token})}'
    # Independent requests (userinfo needs only the raw access_token, not tokeninfo's
    # result) - run them concurrently rather than back-to-back so verification costs one
    # round-trip's latency instead of two.
    with ThreadPoolExecutor(max_workers=2) as executor:
        tokeninfo_future = executor.submit(_get_json, tokeninfo_url)
        userinfo_future = executor.submit(
            _get_json, USERINFO_URL, {'Authorization': f'Bearer {access_token}'}
        )
        tokeninfo = tokeninfo_future.result()
        userinfo = userinfo_future.result()

    if tokeninfo is None or userinfo is None:
        return None

    return {**userinfo, 'aud': tokeninfo.get('aud')}
