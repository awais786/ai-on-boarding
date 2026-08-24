from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from api import views
from api.models import PasswordResetCode

EMAIL = 'ada@example.com'
OLD_PASSWORD = 'lovelace1'
NEW_PASSWORD = 'babbage22'


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

    def explode(*_args, **_kwargs):
        raise OSError('mail server is down')

    monkeypatch.setattr('api.views.send_mail', explode)

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

    response = client.post(page_url(code), {'password': NEW_PASSWORD})

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
    client.post(page_url(used), {'password': NEW_PASSWORD})
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

    response = client.post(page_url(code), {'password': 'short1'})

    assert 'name="password"' in response.content.decode()
    account.refresh_from_db()
    assert account.check_password(OLD_PASSWORD)


@pytest.mark.django_db
def test_the_page_cannot_be_used_twice(client, account, mailoutbox):
    code = issue_code(client, mailoutbox)
    client.post(page_url(code), {'password': NEW_PASSWORD})

    replay = client.post(page_url(code), {'password': 'ontheway3'})

    assert 'name="password"' not in replay.content.decode()
    account.refresh_from_db()
    assert account.check_password(NEW_PASSWORD)


@pytest.mark.django_db
def test_the_page_invalidates_a_token_held_beforehand(client, account, mailoutbox):
    token = Token.objects.create(user=account)
    code = issue_code(client, mailoutbox)

    client.post(page_url(code), {'password': NEW_PASSWORD})

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
    client.post(page_url(code), {'password': NEW_PASSWORD})  # spend it

    replay = client.post(page_url(code), {'password': 'short1'})

    body = replay.content.decode()
    assert 'name="password"' not in body
    assert 'That reset link is not valid.' in body


@pytest.mark.django_db
def test_a_dead_link_answers_the_same_way_to_get_and_post(client, account, mailoutbox):
    """Regression: GET inlined its own refusal and answered 200 where POST answered 400."""
    code = issue_code(client, mailoutbox)
    client.post(page_url(code), {'password': NEW_PASSWORD})

    got = client.get(page_url(code))
    posted = client.post(page_url(code), {'password': NEW_PASSWORD})

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
