from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from api.models import SigninAttempt


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username='ada', email='ada@example.com', password='lovelace1'
    )


def signin(client, email_or_username, password='lovelace1'):
    return client.post(
        '/api/signin/',
        {'email_or_username': email_or_username, 'password': password},
        format='json',
    )


@pytest.mark.django_db
def test_signin_requires_email_or_username(client):
    response = client.post('/api/signin/', {'password': 'lovelace1'}, format='json')

    assert response.status_code == 401
    assert 'email_or_username' in response.data


@pytest.mark.django_db
def test_signin_requires_password(client, user):
    response = client.post(
        '/api/signin/', {'email_or_username': 'ada@example.com'}, format='json'
    )

    assert response.status_code == 401

from api.models import SigninAttempt
from embargo.models import BlockedCountry
from embargo.rules import record_account_country


def create_account(email='ada@example.com', password='lovelace1', country=None):
    user = User.objects.create_user(username=email, email=email, password=password)
    if country is not None:
        record_account_country(user, country)
    return user


def signin(client, email='ada@example.com', password='lovelace1'):
    return client.post('/api/signin/', {'email': email, 'password': password}, format='json')


@pytest.mark.django_db
def test_signin_requires_email(client):
    response = client.post('/api/signin/', {'password': 'lovelace1'}, format='json')

    assert response.status_code == 400
    assert 'email' in response.data


@pytest.mark.django_db
def test_signin_requires_password(client):
    response = client.post('/api/signin/', {'email': 'ada@example.com'}, format='json')

    assert response.status_code == 400
    assert 'password' in response.data


@pytest.mark.django_db
def test_signin_succeeds_by_email(client, user):
    response = signin(client, 'ada@example.com')

    assert response.status_code == 200
    assert response.data['token']


@pytest.mark.django_db
def test_signin_succeeds_by_username(client, user):
    response = signin(client, 'ada')

    assert response.status_code == 200
    assert response.data['token']


@pytest.mark.django_db
def test_signin_email_match_is_case_insensitive(client, user):
    response = signin(client, 'ADA@EXAMPLE.COM')

    assert response.status_code == 200


@pytest.mark.django_db
def test_signin_username_match_is_case_insensitive(client, user):
    response = signin(client, 'ADA')
def test_signin_succeeds_with_correct_credentials(client):
    create_account()

    response = signin(client)

    assert response.status_code == 200
    assert 'token' in response.data


@pytest.mark.django_db
def test_signin_response_contains_only_token(client):
    create_account()

    response = signin(client)

    assert set(response.data.keys()) == {'token'}


@pytest.mark.django_db
def test_signin_case_insensitive_email_match(client):
    create_account(email='ada@example.com')

    response = signin(client, email='ADA@EXAMPLE.COM')

    assert response.status_code == 200


@pytest.mark.django_db
def test_signin_repeated_signin_succeeds_again(client, user):
    first = signin(client, 'ada@example.com')
    second = signin(client, 'ada@example.com')

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.data['token'] == second.data['token']


@pytest.mark.django_db
def test_signin_response_shape_is_token_only(client, user):
    response = signin(client, 'ada@example.com')

    assert response.status_code == 200
    assert set(response.data.keys()) == {'token'}
    assert response.data['token'] == Token.objects.get(user=user).key


@pytest.mark.django_db
def test_signin_rejects_unregistered_email_or_username(client):
    response = signin(client, 'nobody@example.com')
def test_signin_repeated_with_same_credentials_succeeds_again(client):
    create_account()
    first = signin(client)

    second = signin(client)

    assert first.status_code == 200
    assert second.status_code == 200


@pytest.mark.django_db
def test_signin_rejects_unregistered_email(client):
    response = signin(client, email='ghost@example.com')

    assert response.status_code == 401


@pytest.mark.django_db
def test_signin_rejects_wrong_password(client):
    create_account()

    response = signin(client, password='wrongpass1')

    assert response.status_code == 401


@pytest.mark.django_db
def test_signin_rejects_wrong_password(client, user):
    response = signin(client, 'ada@example.com', password='wrongpassword')

    assert response.status_code == 401


@pytest.mark.django_db
def test_signin_unregistered_email_or_username_and_wrong_password_are_identical(client, user):
    unregistered = signin(client, 'nobody@example.com')
    wrong_password = signin(client, 'ada@example.com', password='wrongpassword')

    assert unregistered.status_code == wrong_password.status_code == 401
    assert unregistered.data == wrong_password.data


@pytest.mark.django_db
def test_signin_response_never_contains_password(client, user):
    response = signin(client, 'ada@example.com', password='wrongpassword')

    assert 'password' not in response.data
    assert 'wrongpassword' not in response.content.decode()


@pytest.mark.django_db
def test_signin_locks_out_after_third_failure(client, user):
    for _ in range(3):
        signin(client, 'ada@example.com', password='wrongpassword')

    response = signin(client, 'ada@example.com', password='lovelace1')

    assert response.status_code == 401


@pytest.mark.django_db
def test_signin_lockout_matches_wrong_password_response(client, user):
    for _ in range(3):
        signin(client, 'ada@example.com', password='wrongpassword')

    locked_out = signin(client, 'ada@example.com', password='lovelace1')
    wrong_password = signin(client, 'nobody@example.com', password='wrongpassword')

    assert locked_out.status_code == wrong_password.status_code == 401
def test_signin_unregistered_email_and_wrong_password_are_identical(client):
    create_account()
    unregistered = signin(client, email='ghost@example.com', password='whatever1')

    wrong_password = signin(client, password='wrongpass1')

    assert unregistered.status_code == wrong_password.status_code
    assert unregistered.data == wrong_password.data


@pytest.mark.django_db
def test_signin_never_returns_password(client):
    create_account()

    response = signin(client, password='wrongpass1')

    assert 'lovelace1' not in response.content.decode()
    assert 'wrongpass1' not in response.content.decode()


@pytest.mark.django_db
def test_signin_lockout_after_third_failure(client):
    create_account()
    signin(client, password='wrongpass1')
    signin(client, password='wrongpass1')
    signin(client, password='wrongpass1')

    response = signin(client, password='lovelace1')

    assert response.status_code == 401


@pytest.mark.django_db
def test_signin_lockout_expires_after_window(client):
    create_account()
    signin(client, password='wrongpass1')
    signin(client, password='wrongpass1')
    signin(client, password='wrongpass1')
    attempt = SigninAttempt.objects.get(email='ada@example.com')
    attempt.last_failed_at = timezone.now() - timedelta(minutes=31)
    attempt.save(update_fields=['last_failed_at'])

    response = signin(client, password='lovelace1')

    assert response.status_code == 200


@pytest.mark.django_db
def test_signin_lockout_rejection_matches_wrong_password_rejection(client):
    create_account(email='ada@example.com', password='lovelace1')
    create_account(email='grace@example.com', password='hopper1')
    signin(client, email='ada@example.com', password='wrongpass1')
    signin(client, email='ada@example.com', password='wrongpass1')
    signin(client, email='ada@example.com', password='wrongpass1')

    locked_out = signin(client, email='ada@example.com', password='lovelace1')
    wrong_password = signin(client, email='grace@example.com', password='wrongpass1')

    assert locked_out.status_code == wrong_password.status_code
    assert locked_out.data == wrong_password.data


@pytest.mark.django_db
def test_signin_lockout_expires_after_30_minutes(client, user):
    for _ in range(3):
        signin(client, 'ada@example.com', password='wrongpassword')

    attempt = SigninAttempt.objects.get(email_or_username='ada@example.com')
    attempt.last_failed_at = timezone.now() - timedelta(minutes=31)
    attempt.save()

    response = signin(client, 'ada@example.com', password='lovelace1')

    assert response.status_code == 200


@pytest.mark.django_db
def test_signin_lockout_applies_regardless_of_email_or_username_form(client, user):
    signin(client, 'ada@example.com', password='wrongpassword')
    signin(client, 'ada', password='wrongpassword')
    signin(client, 'ADA@EXAMPLE.COM', password='wrongpassword')

    response = signin(client, 'ada', password='lovelace1')
def test_signin_success_resets_failure_count(client):
    create_account()
    signin(client, password='wrongpass1')
    signin(client, password='wrongpass1')

    signin(client, password='lovelace1')

    attempt = SigninAttempt.objects.get(email='ada@example.com')
    assert attempt.failed_count == 0


@pytest.mark.django_db
def test_signin_rejects_embargoed_account(client):
    create_account(country='India')

    response = signin(client)

    assert response.status_code == 401


@pytest.mark.django_db
def test_signin_success_resets_failure_count(client, user):
    signin(client, 'ada@example.com', password='wrongpassword')
    signin(client, 'ada@example.com', password='wrongpassword')
    signin(client, 'ada@example.com', password='lovelace1')

    attempt = SigninAttempt.objects.get(email_or_username='ada@example.com')
    assert attempt.failed_count == 0

    # after a reset, two more failures should not trigger lockout yet
    signin(client, 'ada@example.com', password='wrongpassword')
    signin(client, 'ada@example.com', password='wrongpassword')
    response = signin(client, 'ada@example.com', password='lovelace1')

    assert response.status_code == 200
def test_signin_country_blocked_after_signup_locks_out_next_attempt(client):
    create_account(country='Freedonia')
    first = signin(client)

    BlockedCountry.objects.create(country='Freedonia')
    second = signin(client)

    assert first.status_code == 200
    assert second.status_code == 401


@pytest.mark.django_db
def test_signin_country_unblocked_after_being_blocked_allows_signin(client):
    create_account(country='Freedonia')
    blocked = BlockedCountry.objects.create(country='Freedonia')
    first = signin(client)

    blocked.delete()
    second = signin(client)

    assert first.status_code == 401
    assert second.status_code == 200


@pytest.mark.django_db
def test_signin_embargo_rejection_matches_wrong_password_rejection(client):
    create_account(email='ada@example.com', password='lovelace1', country='India')
    create_account(email='grace@example.com', password='hopper1')

    embargoed = signin(client, email='ada@example.com', password='lovelace1')
    wrong_password = signin(client, email='grace@example.com', password='wrongpass1')

    assert embargoed.status_code == wrong_password.status_code
    assert embargoed.data == wrong_password.data


@pytest.mark.django_db
def test_signin_embargo_rejection_does_not_increment_failure_count(client):
    create_account(country='India')

    signin(client)

    assert not SigninAttempt.objects.filter(email='ada@example.com').exists()
