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
