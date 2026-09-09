"""Tests for specs/mcp-session-auth/spec.md, written from the spec.

Each requirement and what a test has to observe to protect it:

- Establish a session credential at login -> count the exchanges made across a
  session's first call, and check the credential is kept rather than re-derived.
- Admit a caller with no matching account, without a session credential -> a
  caller Django won't issue a credential to (no account, or embargoed - Django's
  own response cannot tell the two apart) still gets a usable session, just with
  no credential.
- Refuse a tool call made without a session credential -> a tool other than
  signup refuses such a caller and tells them to sign up; signup itself grants a
  credential without a new session.
- Refuse a caller Google does not recognise -> Google's own refusal still blocks
  the session outright.
- Reuse the session credential for every tool call -> later calls, and calls to a
  different tool, add no exchanges and carry the same token to Django.
- Keep Google (and Django) out of the request path after login -> decoding an
  already-issued session token again adds no calls to either.
- Recover once from a rejected session credential -> a refused token is replaced
  and the call retried; the replacement is exchanged exactly once. Because the
  Django token lives inside the signed session token, the replacement covers
  only that one call - it can't be written back in, so a still-stale credential
  keeps needing this same recovery on every later call until the client
  refreshes its session token.
- Fail a call whose recovery does not succeed -> the caller is told to sign in.
- Confine a session credential to its own caller -> two sessions never cross.
- Keep the session credential out of tool results -> no credential appears in a
  result or in a failure, asserted directly rather than through a success path.
"""

import pytest

import auth as credentials
import server
import tools
from clients.base_client import BackendAPIError

GOOGLE_A = 'google-token-a'
GOOGLE_B = 'google-token-b'


def django_tokens_used(django):
    return [record[1] for record in django.calls]


# --- Establish a session credential at login ---------------------------------


async def test_first_tool_call_of_a_session_exchanges_the_google_token_once(
    sign_in, django
):
    await sign_in(GOOGLE_A)
    await tools.users.list_signup_users()

    assert django.exchange_count == 1
    assert django.exchanges == [GOOGLE_A]


async def test_the_exchanged_token_is_retained_as_the_session_credential(sign_in):
    verified = await sign_in(GOOGLE_A)

    assert verified.claims[credentials.BACKEND_TOKEN_CLAIM] == f'drf-for-{GOOGLE_A}'


# --- Admit a caller with no matching account, without a session credential ---


async def test_a_caller_with_no_account_here_is_admitted_with_no_credential(sign_in, django):
    django.exchange_error = BackendAPIError('No account.', no_account=True)

    verified = await sign_in(GOOGLE_A)

    assert verified is not None
    assert credentials.BACKEND_TOKEN_CLAIM not in verified.claims


async def test_an_embargoed_caller_is_admitted_with_no_credential(sign_in, django):
    django.exchange_error = BackendAPIError('That Google account cannot sign in here.', no_account=True)

    verified = await sign_in(GOOGLE_A)

    assert verified is not None
    assert credentials.BACKEND_TOKEN_CLAIM not in verified.claims


async def test_a_no_credential_session_is_not_re_exchanged_on_a_later_decode(sign_in, django):
    django.exchange_error = BackendAPIError('No account.', no_account=True)
    verified = await sign_in(GOOGLE_A)
    exchanges_so_far = django.exchange_count

    # A later request decodes the same already-issued session token - the
    # Django exchange only ever runs once, at issuance.
    await server.auth.load_access_token(verified.token)

    assert django.exchange_count == exchanges_so_far


# --- Refuse a tool call made without a session credential ---------------------


async def test_a_tool_requiring_a_credential_refuses_a_credential_less_caller(sign_in, django):
    django.exchange_error = BackendAPIError('No account.', no_account=True)
    await sign_in(GOOGLE_A)

    with pytest.raises(BackendAPIError) as failure:
        await tools.users.list_signup_users()

    assert 'signup' in str(failure.value).lower()


async def test_signing_up_succeeds_for_a_credential_less_caller(
    sign_in, django, drive_secret_tool
):
    """Unlike the old cache-backed design, signup can't retroactively grant a
    credential for the rest of this session - the Django token lives inside
    the session token the caller already has, which is immutable. Signup
    itself still succeeds; using other tools afterward needs a fresh session
    token (see test_the_replacement_credential_is_not_kept_for_later_calls for
    the same tradeoff on the recovery path)."""
    django.exchange_error = BackendAPIError('No account.', no_account=True)
    await sign_in(GOOGLE_A)
    django.exchange_error = None

    _, result = await drive_secret_tool(
        lambda: tools.account.signup('ada@example.com', 'ada', 'GB'), {'password': 'lovelace1'}
    )

    assert result == {'detail': 'Account created.'}


# --- Refuse a caller Google does not recognise -------------------------------


async def test_a_caller_google_refuses_reaches_no_tool(sign_in, google, django):
    google.refuse.add(GOOGLE_A)

    assert await sign_in(GOOGLE_A) is None
    assert django.exchange_count == 0


# --- Reuse the session credential for every tool call ------------------------


async def test_a_later_tool_call_reuses_the_credential_without_exchanging_again(
    sign_in, django
):
    await sign_in(GOOGLE_A)
    await tools.users.list_signup_users()
    await tools.users.list_signup_users()

    assert django.exchange_count == 1
    assert django_tokens_used(django) == [f'drf-for-{GOOGLE_A}'] * 2


async def test_two_different_tools_in_one_session_use_the_same_credential(
    sign_in, django, drive_secret_tool
):
    await sign_in(GOOGLE_A)
    await tools.users.list_signup_users()
    await drive_secret_tool(
        lambda: tools.users.change_user_password('ada'), {'new_password': 'new-password-1'}
    )

    assert django.exchange_count == 1
    assert set(django_tokens_used(django)) == {f'drf-for-{GOOGLE_A}'}


# --- Keep Google (and Django) out of the request path after login ------------


async def test_serving_a_later_request_makes_no_google_or_django_call(sign_in, google, django):
    verified = await sign_in(GOOGLE_A)
    calls_after_login = google.call_count
    exchanges_after_login = django.exchange_count

    # What FastMCP does on every subsequent request - decode the same
    # already-issued session token - then the tool it guards.
    await server.auth.load_access_token(verified.token)
    await tools.users.list_signup_users()

    assert google.call_count == calls_after_login
    assert django.exchange_count == exchanges_after_login


# --- Recover once from a rejected session credential -------------------------


async def test_a_refused_credential_is_replaced_and_the_call_retried(sign_in, django):
    await sign_in(GOOGLE_A)
    django.rejects.add(f'drf-for-{GOOGLE_A}')
    django.next_tokens = ['drf-replacement']

    result = await tools.users.list_signup_users()

    assert result == [{'username': '***', 'country': 'GB', 'date_joined': '2026-01-01'}]
    assert django_tokens_used(django) == [f'drf-for-{GOOGLE_A}', 'drf-replacement']


async def test_recovery_exchanges_at_most_once_for_a_single_call(sign_in, django):
    await sign_in(GOOGLE_A)
    django.rejects.add(f'drf-for-{GOOGLE_A}')
    django.next_tokens = ['drf-replacement']

    await tools.users.list_signup_users()

    assert django.exchange_count == 2  # one at login, one for the recovery


async def test_the_replacement_credential_is_not_kept_for_later_calls(sign_in, django):
    """Unlike the old cache-backed design, a recovered token can't be written
    back into an already-issued session token - it only covers the one call
    that triggered it."""
    verified = await sign_in(GOOGLE_A)
    django.rejects.add(f'drf-for-{GOOGLE_A}')
    django.next_tokens = ['drf-replacement']
    await tools.users.list_signup_users()

    # Decoding the same session token again still carries the original,
    # by-now-stale credential - nothing server-side remembers the replacement.
    redecoded = await server.auth.load_access_token(verified.token)

    assert redecoded.claims[credentials.BACKEND_TOKEN_CLAIM] == f'drf-for-{GOOGLE_A}'


async def test_a_403_from_django_triggers_no_re_exchange(sign_in, django, drive_secret_tool):
    await sign_in(GOOGLE_A)
    django.error = BackendAPIError('Only an admin may do that.')

    with pytest.raises(BackendAPIError) as refusal:
        await drive_secret_tool(
            lambda: tools.users.change_user_password('ada'), {'new_password': 'new-password-1'}
        )

    assert django.exchange_count == 1
    assert str(refusal.value) == 'Only an admin may do that.'


# --- Fail a call whose recovery does not succeed -----------------------------


async def test_a_call_fails_when_the_replacement_is_also_refused(sign_in, django):
    await sign_in(GOOGLE_A)
    django.rejects.add(f'drf-for-{GOOGLE_A}')
    django.next_tokens = ['drf-replacement']
    django.rejects.add('drf-replacement')

    with pytest.raises(BackendAPIError) as failure:
        await tools.users.list_signup_users()

    assert 'sign in again' in str(failure.value).lower()


async def test_a_call_fails_when_the_fresh_exchange_itself_fails(sign_in, django):
    await sign_in(GOOGLE_A)
    django.rejects.add(f'drf-for-{GOOGLE_A}')
    django.exchange_error = BackendAPIError('No account.', stale_credential=True)

    with pytest.raises(BackendAPIError) as failure:
        await tools.users.list_signup_users()

    assert 'sign in again' in str(failure.value).lower()


async def test_a_stale_credential_keeps_failing_every_call_until_the_client_signs_in_again(
    sign_in, django
):
    """The tradeoff of baking the Django token into the session token: recovery
    can't persist, so a still-stale credential pays the same failed-retry cost
    on every call - it never gets fixed in place. A fresh sign_in (what a real
    client does on session refresh) is what actually clears it."""
    await sign_in(GOOGLE_A)
    django.rejects.add(f'drf-for-{GOOGLE_A}')
    django.exchange_error = BackendAPIError('Could not reach the API.')

    with pytest.raises(BackendAPIError):
        await tools.users.list_signup_users()
    with pytest.raises(BackendAPIError):
        await tools.users.list_signup_users()

    django.exchange_error = None
    django.rejects.clear()
    await sign_in(GOOGLE_A)  # a fresh login/refresh mints a new session token
    result = await tools.users.list_signup_users()

    assert result == [{'username': '***', 'country': 'GB', 'date_joined': '2026-01-01'}]


# --- Confine a session credential to its own caller --------------------------


async def test_each_caller_uses_their_own_credential(sign_in, as_caller, google, django):
    google.subjects = {GOOGLE_A: 'sub-a', GOOGLE_B: 'sub-b'}
    caller_a = await sign_in(GOOGLE_A)
    caller_b = await sign_in(GOOGLE_B)

    as_caller(caller_a)
    await tools.users.list_signup_users()
    as_caller(caller_b)
    await tools.users.list_signup_users()

    assert django_tokens_used(django) == [f'drf-for-{GOOGLE_A}', f'drf-for-{GOOGLE_B}']


async def test_one_callers_credential_is_never_served_to_another(sign_in, google):
    google.subjects = {GOOGLE_A: 'sub-a', GOOGLE_B: 'sub-b'}
    caller_a = await sign_in(GOOGLE_A)
    caller_b = await sign_in(GOOGLE_B)

    assert (
        caller_a.claims[credentials.BACKEND_TOKEN_CLAIM]
        != caller_b.claims[credentials.BACKEND_TOKEN_CLAIM]
    )
    assert caller_a.subject != caller_b.subject


# --- Keep the session credential out of tool results -------------------------


async def test_a_tool_result_carries_no_credential(sign_in):
    await sign_in(GOOGLE_A)

    result = await tools.users.list_signup_users()

    rendered = repr(result)
    assert GOOGLE_A not in rendered
    assert f'drf-for-{GOOGLE_A}' not in rendered


async def test_a_failure_carries_no_credential(sign_in, django):
    await sign_in(GOOGLE_A)
    django.rejects.add(f'drf-for-{GOOGLE_A}')
    django.next_tokens = ['drf-replacement']
    django.rejects.add('drf-replacement')

    with pytest.raises(BackendAPIError) as failure:
        await tools.users.list_signup_users()

    message = str(failure.value)
    assert GOOGLE_A not in message
    assert f'drf-for-{GOOGLE_A}' not in message
    assert 'drf-replacement' not in message


async def test_the_password_a_caller_supplies_never_appears_in_a_result(
    sign_in, django, drive_secret_tool
):
    await sign_in(GOOGLE_A)

    _, result = await drive_secret_tool(
        lambda: tools.users.change_user_password('ada'), {'new_password': 'a-secret-password1'}
    )

    assert 'a-secret-password1' not in repr(result)


# --- An unreachable Django ---------------------------------------------------


async def test_a_caller_is_told_to_sign_in_when_django_cannot_be_reached(
    sign_in, django
):
    await sign_in(GOOGLE_A)
    django.rejects.add(f'drf-for-{GOOGLE_A}')
    django.exchange_error = BackendAPIError('Could not reach the API.')

    with pytest.raises(BackendAPIError) as failure:
        await tools.users.list_signup_users()

    assert 'sign in again' in str(failure.value).lower()


async def test_no_session_is_established_when_django_cannot_be_reached(sign_in, django):
    django.exchange_error = BackendAPIError('Could not reach the API.')

    with pytest.raises(BackendAPIError):
        await sign_in(GOOGLE_A)


# --- The FastMCP-signed session token is what's actually verified ------------


async def test_a_tampered_session_token_is_refused():
    assert await server.auth.load_access_token('not-a-real-token') is None


async def test_a_session_token_from_a_different_signing_key_is_refused(sign_in):
    from fastmcp.server.auth.jwt_issuer import JWTIssuer

    verified = await sign_in(GOOGLE_A)
    forger = JWTIssuer(issuer=server.auth.jwt_issuer.issuer, audience=server.auth.jwt_issuer.audience, signing_key=b'0' * 32)
    forged = forger.issue_access_token(
        client_id='attacker', scopes=['openid'], jti='forged', upstream_claims=verified.claims
    )

    assert await server.auth.load_access_token(forged) is None
