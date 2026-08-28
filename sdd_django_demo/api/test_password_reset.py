from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from api import views
from api.models import PasswordResetCode, hash_reset_code

EMAIL = 'ada@example.com'
OLD_PASSWORD = 'lovelace1'
NEW_PASSWORD = 'babbage22'


@pytest.fixture(autouse=True)
def _isolate_throttle_counters():
    """Give every test its own rate-limit budget.

    The reset endpoint counts requests per address in Django's cache, which lives
    for the whole process. Without clearing it, one test's requests limit the next
    and the failures land far from their cause.
    """
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def account():
    return User.objects.create_user(username=EMAIL, email=EMAIL, password=OLD_PASSWORD)


def request_reset(client, email=EMAIL):
    return client.post('/api/password-reset/', {'email': email}, format='json')


def confirm(client, code, password=NEW_PASSWORD):
    return client.post(
        '/api/password-reset/confirm/', {'code': code, 'password': password}, format='json'
    )


def link_from(mailoutbox):
    return next(w for w in mailoutbox[-1].body.split() if w.startswith('http'))


def code_from(mailoutbox):
    return link_from(mailoutbox).rstrip('/').rsplit('/', 1)[-1]


def _explode(*_args, **_kwargs):
    raise OSError('mail server is down')


def issue_code(client, mailoutbox, email=EMAIL):
    request_reset(client, email)
    return code_from(mailoutbox)


# Requirement: Accept a reset request


@pytest.mark.django_db
def test_reset_request_with_an_email_is_accepted(client):
    assert request_reset(client).status_code == 200


# Requirement: Reject a reset request with no email


@pytest.mark.django_db
def test_reset_request_without_an_email_names_the_email_field(client):
    response = client.post('/api/password-reset/', {}, format='json')

    assert response.status_code == 400
    assert 'email' in response.data


@pytest.mark.django_db
@pytest.mark.parametrize('body', ['["a"]', '"hello"', '123'], ids=['list', 'string', 'number'])
def test_a_body_that_is_not_an_object_is_refused_not_raised(client, body):
    """A malformed body must be answered, not crash the endpoint.

    The per-address limit reads the body before any serializer does, so a payload
    that parses to something other than an object reaches it unvalidated. Asking
    such a payload for a field used to raise, which the caller saw as a 500.
    """
    response = client.post('/api/password-reset/', body, content_type='application/json')

    assert response.status_code == 400


@pytest.mark.django_db
@pytest.mark.parametrize('body', ['["a"]', '"hello"', '123'], ids=['list', 'string', 'number'])
def test_a_malformed_body_is_refused_the_same_way_on_both_endpoints(client, body):
    """The endpoint with a limit in front of it answers like the one without."""
    requested = client.post('/api/password-reset/', body, content_type='application/json')
    confirmed = client.post(
        '/api/password-reset/confirm/', body, content_type='application/json'
    )

    assert requested.status_code == confirmed.status_code
    assert requested.content == confirmed.content


# Requirement: Answer every reset request identically


@pytest.mark.django_db
def test_registered_and_unregistered_addresses_get_identical_answers(client, account):
    registered = request_reset(client, EMAIL)
    unregistered = request_reset(client, 'nobody@example.com')

    assert registered.status_code == unregistered.status_code == 200
    assert registered.data == unregistered.data


# Requirement: Deliver a reset code to a registered address


@pytest.mark.django_db
def test_a_registered_address_is_sent_a_link_carrying_a_code(client, account, mailoutbox):
    request_reset(client)

    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == [EMAIL]
    assert PasswordResetCode.resolve(code_from(mailoutbox)) is not None


# Requirement: Deliver the reset link as an absolute address


@pytest.mark.django_db
def test_the_delivered_link_is_absolute(client, account, mailoutbox):
    request_reset(client)

    assert link_from(mailoutbox).startswith('http://localhost:8000/')


@pytest.mark.django_db
def test_the_link_host_comes_from_the_setting_not_the_request(
    client, account, mailoutbox, settings
):
    """A forged Host must not steer where the reset link points."""
    settings.ALLOWED_HOSTS = ['*']

    client.post(
        '/api/password-reset/', {'email': EMAIL}, format='json', HTTP_HOST='evil.example.com'
    )

    assert 'evil.example.com' not in link_from(mailoutbox)
    assert link_from(mailoutbox).startswith('http://localhost:8000/')


@pytest.mark.django_db
def test_a_dead_mail_server_does_not_make_addresses_distinguishable(
    client, account, monkeypatch
):
    """Regression: a delivery error must not turn into a 500 for known addresses only."""

    monkeypatch.setattr('api.views.send_mail', _explode)

    registered = request_reset(client, EMAIL)
    unregistered = request_reset(client, 'nobody@example.com')

    assert registered.status_code == unregistered.status_code == 200
    assert registered.data == unregistered.data


@pytest.mark.django_db
def test_a_failure_issuing_the_code_does_not_make_addresses_distinguishable(
    client, account, monkeypatch
):
    """Regression: the guard must cover the whole registered-only branch, not just the send."""

    def explode(*_args, **_kwargs):
        raise IntegrityError('could not issue')

    monkeypatch.setattr('api.views.PasswordResetCode.issue_for', explode)

    registered = request_reset(client, EMAIL)
    unregistered = request_reset(client, 'nobody@example.com')

    assert registered.status_code == unregistered.status_code == 200
    assert registered.data == unregistered.data


@pytest.mark.django_db
def test_an_account_stored_with_mixed_case_still_receives_a_link(client, mailoutbox):
    """Regression: accounts made outside signup keep the case they were created with."""
    User.objects.create_user(
        username='mixed@example.com', email='Ada@Example.COM', password=OLD_PASSWORD
    )

    request_reset(client, 'ada@example.com')

    assert len(mailoutbox) == 1
    assert PasswordResetCode.resolve(code_from(mailoutbox)) is not None


# Requirement: Deliver nothing to an unregistered address


@pytest.mark.django_db
def test_an_unregistered_address_is_sent_nothing(client, mailoutbox):
    request_reset(client, 'nobody@example.com')

    assert mailoutbox == []


# Requirement: Never return the reset code in a response


@pytest.mark.django_db
def test_the_response_carries_neither_the_code_nor_the_link(client, account, mailoutbox):
    response = request_reset(client)

    body = str(response.data)
    assert code_from(mailoutbox) not in body
    assert link_from(mailoutbox) not in body


@pytest.mark.django_db
def test_the_stored_code_is_a_digest_rather_than_the_code(client, account, mailoutbox):
    request_reset(client)
    code = code_from(mailoutbox)

    assert not PasswordResetCode.objects.filter(code_digest=code).exists()
    assert PasswordResetCode.objects.filter(user=account).exists()


# Requirement: Accept a reset completion


@pytest.mark.django_db
def test_a_completion_with_a_valid_code_is_accepted(client, account, mailoutbox):
    assert confirm(client, issue_code(client, mailoutbox)).status_code == 200


# Requirement: Reject a reset completion with missing fields


@pytest.mark.django_db
def test_a_completion_without_a_code_names_the_code_field(client):
    response = client.post(
        '/api/password-reset/confirm/', {'password': NEW_PASSWORD}, format='json'
    )

    assert response.status_code == 400
    assert 'code' in response.data


@pytest.mark.django_db
def test_a_completion_without_a_password_names_the_password_field(client):
    response = client.post('/api/password-reset/confirm/', {'code': 'anything'}, format='json')

    assert response.status_code == 400
    assert 'password' in response.data


# Requirement: Complete a reset with a valid code


@pytest.mark.django_db
def test_a_completed_reset_changes_the_password(client, account, mailoutbox):
    confirm(client, issue_code(client, mailoutbox))

    account.refresh_from_db()
    assert account.check_password(NEW_PASSWORD)


@pytest.mark.django_db
def test_the_previous_password_stops_working(client, account, mailoutbox):
    confirm(client, issue_code(client, mailoutbox))

    account.refresh_from_db()
    assert not account.check_password(OLD_PASSWORD)


# Requirement: Hold a new password to the signup strength rules


@pytest.mark.django_db
def test_a_password_signup_would_reject_is_refused(client, account, mailoutbox):
    response = confirm(client, issue_code(client, mailoutbox), password='short1')

    assert response.status_code == 400
    assert 'password' in response.data


@pytest.mark.django_db
def test_a_refused_weak_password_leaves_the_old_one_working(client, account, mailoutbox):
    confirm(client, issue_code(client, mailoutbox), password='short1')

    account.refresh_from_db()
    assert account.check_password(OLD_PASSWORD)


# Requirement: Expire a reset code after 30 minutes


@pytest.mark.django_db
def test_a_code_older_than_thirty_minutes_is_refused(client, account, mailoutbox):
    code = issue_code(client, mailoutbox)
    PasswordResetCode.objects.filter(user=account).update(
        issued_at=timezone.now() - timedelta(minutes=31)
    )

    assert confirm(client, code).status_code == 400
    account.refresh_from_db()
    assert account.check_password(OLD_PASSWORD)


@pytest.mark.django_db
def test_a_code_inside_the_window_is_accepted(client, account, mailoutbox):
    code = issue_code(client, mailoutbox)
    PasswordResetCode.objects.filter(user=account).update(
        issued_at=timezone.now() - timedelta(minutes=29)
    )

    assert confirm(client, code).status_code == 200


# Requirement: Retire a reset code once it is used


@pytest.mark.django_db
def test_a_used_code_cannot_be_replayed(client, account, mailoutbox):
    code = issue_code(client, mailoutbox)
    confirm(client, code)

    replay = confirm(client, code, password='ontheway3')

    assert replay.status_code == 400
    account.refresh_from_db()
    assert account.check_password(NEW_PASSWORD)


@pytest.mark.django_db
def test_issuing_retries_when_the_digest_collides(account, monkeypatch):
    """The retry branch in `issue_for`, which nothing else in the suite reaches.

    A real collision is forced rather than simulated: a row is planted holding the
    digest of the code the generator is about to produce, so `create` raises a
    genuine `IntegrityError` against the unique digest column. The retry generates a
    fresh code, which no longer collides.

    The planted row belongs to another account and is already spent, so it cannot
    satisfy the request by accident or trip the one-usable-code-per-user index.
    """
    stranger = User.objects.create_user(username='taken@example.com', email='taken@example.com')
    PasswordResetCode.objects.create(
        user=stranger, code_digest=hash_reset_code('collide'), usable=False
    )

    generated = ['collide', 'fresh-code-that-does-not-collide']
    monkeypatch.setattr('api.models.secrets.token_urlsafe', lambda _n: generated.pop(0))

    code = PasswordResetCode.issue_for(account)

    # The first code was consumed by the failed attempt, so the retry ran.
    assert not generated, 'the retry did not run: the second code was never generated'
    assert code == 'fresh-code-that-does-not-collide'
    assert PasswordResetCode.resolve(code) is not None


@pytest.mark.django_db
def test_issuing_gives_up_when_the_collision_persists(account, monkeypatch):
    """One retry, not a loop: a second failure is not a race and must propagate."""
    stranger = User.objects.create_user(username='taken@example.com', email='taken@example.com')
    PasswordResetCode.objects.create(
        user=stranger, code_digest=hash_reset_code('collide'), usable=False
    )
    monkeypatch.setattr('api.models.secrets.token_urlsafe', lambda _n: 'collide')

    with pytest.raises(IntegrityError):
        PasswordResetCode.issue_for(account)


# Requirement: Supersede an earlier unused code


@pytest.mark.django_db
def test_requesting_again_kills_the_earlier_code(client, account, mailoutbox):
    first = issue_code(client, mailoutbox)
    second = issue_code(client, mailoutbox)

    assert confirm(client, first).status_code == 400
    assert confirm(client, second).status_code == 200


@pytest.mark.django_db
def test_an_account_can_never_hold_two_usable_codes(client, account, mailoutbox):
    """Regression: supersession is a database invariant, not just view sequencing."""
    for _ in range(4):
        request_reset(client)

    assert PasswordResetCode.objects.filter(user=account, usable=True).count() == 1

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            PasswordResetCode.objects.create(user=account, code_digest='a' * 64)


# Requirement: Reject every bad code identically


@pytest.mark.django_db
def test_all_four_unusable_codes_are_refused_identically(client, account, mailoutbox):
    unrecognised = confirm(client, 'no-such-code')

    expired = issue_code(client, mailoutbox)
    PasswordResetCode.objects.filter(user=account).update(
        issued_at=timezone.now() - timedelta(minutes=31)
    )
    expired_response = confirm(client, expired)

    used = issue_code(client, mailoutbox)
    confirm(client, used)
    used_response = confirm(client, used)

    superseded = issue_code(client, mailoutbox)
    issue_code(client, mailoutbox)
    superseded_response = confirm(client, superseded)

    responses = [unrecognised, expired_response, used_response, superseded_response]
    assert {r.status_code for r in responses} == {400}
    assert all(r.data == unrecognised.data for r in responses)


# Requirement: Return HTTP 400 when a reset completion is refused


@pytest.mark.django_db
def test_a_refused_completion_returns_400(client):
    assert confirm(client, 'no-such-code').status_code == 400


# Requirement: Invalidate existing authentication tokens on reset


@pytest.mark.django_db
def test_a_token_held_before_the_reset_stops_working(client, account, mailoutbox):
    token = Token.objects.create(user=account)

    confirm(client, issue_code(client, mailoutbox))

    assert not Token.objects.filter(key=token.key).exists()


# Requirement: Never return a password


@pytest.mark.django_db
def test_no_reset_response_contains_the_submitted_password(client, account, mailoutbox):
    requested = request_reset(client)
    code = code_from(mailoutbox)
    weak = confirm(client, code, password='short1')
    completed = confirm(client, code)

    for response in (requested, weak, completed):
        assert NEW_PASSWORD not in str(response.data)
        assert OLD_PASSWORD not in str(response.data)


# Requirement: Store a new password unrecoverably


@pytest.mark.django_db
def test_the_new_password_is_not_stored_as_submitted(client, account, mailoutbox):
    confirm(client, issue_code(client, mailoutbox))

    account.refresh_from_db()
    assert account.password != NEW_PASSWORD
    assert account.check_password(NEW_PASSWORD)


# Requirement: Serve a page at the delivered link


def page_url(code):
    return f'/reset-password/{code}/'


def submit_form(client, code, password=NEW_PASSWORD, confirmation=None):
    """Submit the reset page's form, confirming the password unless told otherwise.

    Defaulting the confirmation to the password keeps tests that are about
    something else - expiry, replay, token invalidation - saying only what they
    are about. Tests that are about the confirmation pass it explicitly.
    """
    if confirmation is None:
        confirmation = password
    return client.post(
        page_url(code), {'password': password, 'confirm_password': confirmation}
    )


@pytest.mark.django_db
def test_a_usable_link_opens_a_password_form(client, account, mailoutbox):
    response = client.get(page_url(issue_code(client, mailoutbox)))

    assert response.status_code == 200
    body = response.content.decode()
    assert 'name="password"' in body
    assert '<form' in body


@pytest.mark.django_db
def test_submitting_the_form_completes_the_reset(client, account, mailoutbox):
    code = issue_code(client, mailoutbox)

    response = submit_form(client, code, NEW_PASSWORD)

    assert response.status_code == 200
    account.refresh_from_db()
    assert account.check_password(NEW_PASSWORD)
    assert not account.check_password(OLD_PASSWORD)


@pytest.mark.django_db
def test_every_unusable_link_shows_the_same_page_and_no_form(client, account, mailoutbox):
    unrecognised = client.get(page_url('no-such-code'))

    expired = issue_code(client, mailoutbox)
    PasswordResetCode.objects.filter(user=account).update(
        issued_at=timezone.now() - timedelta(minutes=31)
    )
    expired_page = client.get(page_url(expired))

    used = issue_code(client, mailoutbox)
    submit_form(client, used, NEW_PASSWORD)
    used_page = client.get(page_url(used))

    superseded = issue_code(client, mailoutbox)
    issue_code(client, mailoutbox)
    superseded_page = client.get(page_url(superseded))

    pages = [unrecognised, expired_page, used_page, superseded_page]
    for page in pages:
        assert page.status_code == 400
        assert 'name="password"' not in page.content.decode()
    assert len({p.content for p in pages}) == 1


@pytest.mark.django_db
def test_a_weak_password_keeps_the_form_open(client, account, mailoutbox):
    code = issue_code(client, mailoutbox)

    response = submit_form(client, code, 'short1')

    assert 'name="password"' in response.content.decode()
    account.refresh_from_db()
    assert account.check_password(OLD_PASSWORD)


@pytest.mark.django_db
def test_the_page_cannot_be_used_twice(client, account, mailoutbox):
    code = issue_code(client, mailoutbox)
    submit_form(client, code, NEW_PASSWORD)

    replay = submit_form(client, code, 'ontheway3')

    assert 'name="password"' not in replay.content.decode()
    account.refresh_from_db()
    assert account.check_password(NEW_PASSWORD)


@pytest.mark.django_db
def test_the_page_invalidates_a_token_held_beforehand(client, account, mailoutbox):
    token = Token.objects.create(user=account)
    code = issue_code(client, mailoutbox)

    submit_form(client, code, NEW_PASSWORD)

    assert not Token.objects.filter(key=token.key).exists()


@pytest.mark.django_db
def test_the_link_the_mail_carries_actually_resolves(client, account, mailoutbox):
    """The whole point: the address in the mail must not 404."""
    request_reset(client)
    link = link_from(mailoutbox)

    response = client.get(link.replace('http://localhost:8000', ''))

    assert response.status_code == 200


@pytest.mark.django_db
def test_an_unusable_link_offers_no_form_even_when_the_password_is_weak(
    client, account, mailoutbox
):
    """Regression: a dead link must say so, not render a live form to fill in."""
    code = issue_code(client, mailoutbox)
    submit_form(client, code, NEW_PASSWORD)  # spend it

    replay = submit_form(client, code, 'short1')

    body = replay.content.decode()
    assert 'name="password"' not in body
    assert 'That reset link is not valid.' in body


@pytest.mark.django_db
def test_a_dead_link_answers_the_same_way_to_get_and_post(client, account, mailoutbox):
    """Regression: GET inlined its own refusal and answered 200 where POST answered 400."""
    code = issue_code(client, mailoutbox)
    submit_form(client, code, NEW_PASSWORD)

    got = client.get(page_url(code))
    posted = submit_form(client, code, NEW_PASSWORD)

    assert got.status_code == posted.status_code == 400
    assert got.content == posted.content


@pytest.mark.django_db
def test_response_bodies_are_not_shared_between_requests(client, account):
    """Regression: the body constants were handed to Response by reference."""
    first = request_reset(client)
    first.data['detail'] = 'mutated'
    second = request_reset(client)

    assert second.data['detail'] != 'mutated'
    assert views.RESET_REQUESTED_BODY['detail'] != 'mutated'


@pytest.mark.parametrize(
    'raised, expected',
    [
        ('Too short.', 'Too short.'),
        ({'password': 'Must be at least 8 characters.'}, 'Must be at least 8 characters.'),
        ({'password': ['A.', 'B.']}, 'A. B.'),
    ],
)
def test_validation_messages_render_as_text_not_characters(raised, expected):
    """Regression: ErrorDetail subclasses str, so a dict value was iterated per character."""
    assert views.flatten_messages(ValidationError(raised).detail) == expected


# Requirement: Leave earlier codes usable when delivery fails


@pytest.mark.django_db
def test_a_failed_delivery_leaves_the_earlier_code_usable(
    client, account, mailoutbox, monkeypatch
):
    first = issue_code(client, mailoutbox)
    rows_before = PasswordResetCode.objects.count()

    monkeypatch.setattr('api.views.send_mail', _explode)
    request_reset(client)

    assert PasswordResetCode.resolve(first) is not None
    assert PasswordResetCode.objects.count() == rows_before


@pytest.mark.django_db
def test_a_failed_delivery_is_answered_like_a_successful_one(
    client, account, mailoutbox, monkeypatch
):
    delivered = request_reset(client)

    monkeypatch.setattr('api.views.send_mail', _explode)
    failed = request_reset(client)

    assert delivered.status_code == failed.status_code
    assert delivered.data == failed.data


# Requirement: Limit how often a reset may be requested for one address


@pytest.mark.django_db
def test_requests_beyond_the_limit_issue_and_send_nothing(
    client, account, mailoutbox
):
    for _ in range(5):
        request_reset(client)
    sent_at_limit = len(mailoutbox)
    rows_at_limit = PasswordResetCode.objects.count()

    for _ in range(5):
        request_reset(client)

    assert len(mailoutbox) == sent_at_limit
    assert PasswordResetCode.objects.count() == rows_at_limit


@pytest.mark.django_db
def test_a_flood_cannot_leave_an_address_with_no_usable_code(client, account, mailoutbox):
    """The limit stops the superseding, so the last code delivered stays usable.

    An *earlier* code is not expected to survive - "Supersede an earlier unused
    code" requires the opposite. What matters is that the churn ends.
    """
    for _ in range(20):
        request_reset(client)

    latest = code_from(mailoutbox)
    assert PasswordResetCode.resolve(latest) is not None
    assert confirm(client, latest).status_code == 200


@pytest.mark.django_db
def test_being_limited_does_not_reveal_whether_an_account_exists(
    client, account
):
    for _ in range(6):
        registered = request_reset(client, EMAIL)
    for _ in range(6):
        unregistered = request_reset(client, 'nobody@example.com')

    # Both must actually have been refused: if the limit stopped applying, these two
    # would still match while proving nothing.
    assert registered.status_code == unregistered.status_code == 429
    # Compared as rendered bytes rather than as `.data` - byte-identity is what the
    # requirement asks for, and it is the stronger of the two.
    assert registered.content == unregistered.content


@pytest.mark.django_db
def test_a_request_refused_by_the_limit_returns_429(client, account):
    for _ in range(5):
        request_reset(client)

    assert request_reset(client).status_code == 429


@pytest.mark.django_db
def test_two_refusals_are_identical_however_far_apart_they_are(client, account, monkeypatch):
    """The refusal carries no countdown, so time passing cannot change it.

    The clock the limit reads is moved between the two refusals rather than waiting:
    real elapsed time inside a test is both too small and too variable to show the
    difference this guards against. The framework's default refusal appends the wait
    remaining, rounded up, which would differ across the gap below.
    """
    clock = [1_000_000.0]
    monkeypatch.setattr(
        views.PasswordResetAddressThrottle, 'timer', staticmethod(lambda: clock[0])
    )

    for _ in range(5):
        request_reset(client)
    first = request_reset(client)

    clock[0] += 900  # a quarter of the way through the window

    second = request_reset(client)

    assert first.status_code == second.status_code == 429
    assert first.content == second.content
    # Named directly rather than left to the equality above: a body that happened to
    # carry the same countdown twice would satisfy that check without meaning it.
    assert b'second' not in first.content
    # The header is the other half of what `wait=None` suppresses, and the spec puts
    # headers alongside the body. Asserted separately because the equality above
    # compares bodies only and would not notice it coming back.
    assert 'Retry-After' not in first.headers
    assert 'Retry-After' not in second.headers


@pytest.mark.django_db
def test_malformed_bodies_are_not_a_way_around_the_limit(client, account, mailoutbox):
    """Skipping the limit for a body with no address must open nothing.

    A body carrying no address gives the limit nothing to count against, so it is
    not counted at all. That is only safe because such a request is refused before
    it can issue or send - which is what this asserts, along with the address's own
    allowance being untouched by the flood.
    """
    for _ in range(50):
        client.post('/api/password-reset/', '["a"]', content_type='application/json')

    assert PasswordResetCode.objects.count() == 0
    assert mailoutbox == []

    # The real address still has its full allowance: the flood consumed none of it.
    for _ in range(5):
        assert request_reset(client).status_code == 200
    assert request_reset(client).status_code == 429


@pytest.mark.django_db
def test_the_limit_is_per_address_not_global(client, account, mailoutbox):
    """One address being limited must not stop a different person resetting."""
    User.objects.create_user(username='grace@example.com', email='grace@example.com')
    for _ in range(8):
        request_reset(client, EMAIL)
    before = len(mailoutbox)

    request_reset(client, 'grace@example.com')

    assert len(mailoutbox) == before + 1


# Requirement: Serve a page at the delivered link


@pytest.mark.django_db
def test_the_form_asks_for_the_new_password_twice(client, account, mailoutbox):
    response = client.get(page_url(issue_code(client, mailoutbox)))

    body = response.content.decode()
    assert 'name="password"' in body
    assert 'name="confirm_password"' in body


# Requirement: Require the two password entries to match


@pytest.mark.django_db
def test_two_entries_that_differ_change_nothing(client, account, mailoutbox):
    code = issue_code(client, mailoutbox)

    response = client.post(
        page_url(code), {'password': NEW_PASSWORD, 'confirm_password': 'babbage23'}
    )

    assert 'do not match' in response.content.decode()
    account.refresh_from_db()
    assert account.check_password(OLD_PASSWORD)


@pytest.mark.django_db
def test_a_mismatch_keeps_the_form_open(client, account, mailoutbox):
    code = issue_code(client, mailoutbox)

    response = client.post(
        page_url(code), {'password': NEW_PASSWORD, 'confirm_password': 'babbage23'}
    )

    body = response.content.decode()
    assert 'name="password"' in body
    assert 'name="confirm_password"' in body


@pytest.mark.django_db
def test_a_mismatch_does_not_spend_the_reset_link(client, account, mailoutbox):
    """Asserted directly, not through a later success.

    A mismatch that quietly spent the code would leave someone holding a link that
    stops working the moment they mistype - and nothing in a passing success path
    would notice.
    """
    code = issue_code(client, mailoutbox)

    client.post(page_url(code), {'password': NEW_PASSWORD, 'confirm_password': 'babbage23'})

    still_open = client.get(page_url(code))
    assert still_open.status_code == 200
    assert 'name="password"' in still_open.content.decode()
    assert PasswordResetCode.objects.filter(user=account, usable=True).exists()


@pytest.mark.django_db
def test_an_empty_second_entry_is_a_mismatch(client, account, mailoutbox):
    code = issue_code(client, mailoutbox)

    response = client.post(page_url(code), {'password': NEW_PASSWORD, 'confirm_password': ''})

    assert 'do not match' in response.content.decode()
    account.refresh_from_db()
    assert account.check_password(OLD_PASSWORD)


# Requirement: Report a mismatch before judging the password


@pytest.mark.django_db
def test_a_mismatch_is_reported_ahead_of_a_strength_complaint(client, account, mailoutbox):
    """A weak password that was also mistyped is a typo first, a weak password second."""
    code = issue_code(client, mailoutbox)

    response = client.post(page_url(code), {'password': 'abc', 'confirm_password': 'abd'})

    body = response.content.decode()
    assert 'do not match' in body
    assert 'at least' not in body


@pytest.mark.django_db
def test_strength_is_still_judged_once_the_entries_match(client, account, mailoutbox):
    code = issue_code(client, mailoutbox)

    response = client.post(page_url(code), {'password': 'abc', 'confirm_password': 'abc'})

    body = response.content.decode()
    assert 'at least' in body
    assert 'do not match' not in body
    account.refresh_from_db()
    assert account.check_password(OLD_PASSWORD)


# Requirement: Decide the link before the password


@pytest.mark.django_db
def test_a_dead_link_is_refused_rather_than_reporting_a_mismatch(client, account, mailoutbox):
    """The link's state is decided first, whatever was typed into the form."""
    code = issue_code(client, mailoutbox)
    submit_form(client, code)  # spend it

    replay = client.post(
        page_url(code), {'password': NEW_PASSWORD, 'confirm_password': 'babbage23'}
    )

    body = replay.content.decode()
    assert views.PAGE_REFUSAL in body
    assert 'name="password"' not in body
    assert 'do not match' not in body


# Requirement: Never retain the confirmation entry


@pytest.mark.django_db
def test_the_confirmation_is_not_stored(client, account, mailoutbox):
    code = issue_code(client, mailoutbox)

    submit_form(client, code, NEW_PASSWORD, confirmation=NEW_PASSWORD)

    stored = [
        str(value)
        for record in PasswordResetCode.objects.all()
        for value in (record.code_digest, record.usable, record.issued_at)
    ]
    account.refresh_from_db()
    stored.append(account.password)
    assert not any(NEW_PASSWORD in value for value in stored)


@pytest.mark.django_db
@pytest.mark.parametrize(
    'password,confirmation',
    [
        (NEW_PASSWORD, NEW_PASSWORD),  # completes
        (NEW_PASSWORD, 'babbage23'),  # mismatch
        ('abc', 'abc'),  # too weak
    ],
)
def test_neither_entry_appears_in_any_response(
    client, account, mailoutbox, password, confirmation
):
    code = issue_code(client, mailoutbox)

    response = client.post(
        page_url(code), {'password': password, 'confirm_password': confirmation}
    )

    body = response.content.decode()
    assert password not in body
    assert confirmation not in body


# Requirement: Complete a reset through the API with a single password


@pytest.mark.django_db
def test_the_api_completes_with_one_password_and_no_confirmation(client, account, mailoutbox):
    """The asymmetry is deliberate - see the change's proposal. Pinned so a later
    'let's make these consistent' breaks a test instead of every API caller."""
    code = issue_code(client, mailoutbox)

    response = client.post(
        '/api/password-reset/confirm/', {'code': code, 'password': NEW_PASSWORD}, format='json'
    )

    assert response.status_code == 200
    account.refresh_from_db()
    assert account.check_password(NEW_PASSWORD)
