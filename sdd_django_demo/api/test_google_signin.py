from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from api.models import GoogleIdentity
from embargo.rules import record_account_country

CLIENT_ID = '123456789.apps.googleusercontent.com'
OTHER_CLIENT_ID = '987654321.apps.googleusercontent.com'


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username='ada', email='ada@example.com', password='lovelace1'
    )


def create_account(username='ada', email='ada@example.com', password='lovelace1', country=None):
    account = User.objects.create_user(username=username, email=email, password=password)
    if country is not None:
        record_account_country(account, country)
    return account


def google_claims(**overrides):
    claims = {
        'aud': CLIENT_ID,
        'sub': 'google-sub-1',
        'email': 'ada@example.com',
        'email_verified': True,
        'hd': None,
    }
    claims.update(overrides)
    return claims


def google_signin(client, access_token='a-google-access-token'):
    return client.post('/api/auth/google/', {'access_token': access_token}, format='json')


def signin_with_claims(client, claims, access_token='a-google-access-token'):
    with patch('api.views.verify_google_access_token', return_value=claims):
        return google_signin(client, access_token)


@pytest.mark.django_db
def test_google_signin_requires_access_token(client):
    response = client.post('/api/auth/google/', {}, format='json')

    assert response.status_code == 400
    assert 'access_token' in response.data


@pytest.mark.django_db
def test_google_signin_rejects_invalid_or_expired_token(client, settings, user):
    settings.GOOGLE_OAUTH_ALLOWED_CLIENT_IDS = [CLIENT_ID]

    response = signin_with_claims(client, None)

    assert response.status_code == 401


@pytest.mark.django_db
def test_google_signin_rejects_unrecognised_audience(client, settings, user):
    settings.GOOGLE_OAUTH_ALLOWED_CLIENT_IDS = [CLIENT_ID]

    response = signin_with_claims(client, google_claims(aud=OTHER_CLIENT_ID))

    assert response.status_code == 401


@pytest.mark.django_db
def test_google_signin_succeeds_with_audience_on_the_allowlist(client, settings, user):
    settings.GOOGLE_OAUTH_ALLOWED_CLIENT_IDS = [CLIENT_ID]

    response = signin_with_claims(client, google_claims(aud=CLIENT_ID))

    assert response.status_code == 200


@pytest.mark.django_db
def test_google_signin_rejects_unverified_email(client, settings, user):
    settings.GOOGLE_OAUTH_ALLOWED_CLIENT_IDS = [CLIENT_ID]

    response = signin_with_claims(client, google_claims(email_verified=False))

    assert response.status_code == 401


@pytest.mark.django_db
def test_google_signin_rejects_domain_not_on_configured_allowlist(client, settings, user):
    settings.GOOGLE_OAUTH_ALLOWED_CLIENT_IDS = [CLIENT_ID]
    settings.GOOGLE_OAUTH_ALLOWED_DOMAINS = ['allowed.example']

    response = signin_with_claims(client, google_claims(hd='not-allowed.example'))

    assert response.status_code == 401


@pytest.mark.django_db
def test_google_signin_succeeds_with_domain_on_configured_allowlist(client, settings, user):
    settings.GOOGLE_OAUTH_ALLOWED_CLIENT_IDS = [CLIENT_ID]
    settings.GOOGLE_OAUTH_ALLOWED_DOMAINS = ['allowed.example']

    response = signin_with_claims(client, google_claims(hd='allowed.example'))

    assert response.status_code == 200


@pytest.mark.django_db
def test_google_signin_succeeds_with_no_domain_allowlist_configured_and_hd_present(
    client, settings, user
):
    settings.GOOGLE_OAUTH_ALLOWED_CLIENT_IDS = [CLIENT_ID]

    response = signin_with_claims(client, google_claims(hd='some-workspace.example'))

    assert response.status_code == 200


@pytest.mark.django_db
def test_google_signin_succeeds_with_no_domain_allowlist_configured_and_hd_absent(
    client, settings, user
):
    settings.GOOGLE_OAUTH_ALLOWED_CLIENT_IDS = [CLIENT_ID]

    response = signin_with_claims(client, google_claims(hd=None))

    assert response.status_code == 200


@pytest.mark.django_db
def test_google_signin_rejects_identity_with_no_linked_or_matching_account(client, settings):
    settings.GOOGLE_OAUTH_ALLOWED_CLIENT_IDS = [CLIENT_ID]

    response = signin_with_claims(client, google_claims(email='nobody@example.com'))

    assert response.status_code == 401
    assert not User.objects.filter(email='nobody@example.com').exists()
    assert not GoogleIdentity.objects.exists()


@pytest.mark.django_db
def test_google_signin_rejects_missing_email_even_if_an_account_has_a_blank_email(
    client, settings
):
    settings.GOOGLE_OAUTH_ALLOWED_CLIENT_IDS = [CLIENT_ID]
    User.objects.create_user(username='admin', email='', password='irrelevant1')

    response = signin_with_claims(client, google_claims(email=None))

    assert response.status_code == 401
    assert not GoogleIdentity.objects.exists()


@pytest.mark.django_db
def test_google_signin_rejects_claims_with_no_sub(client, settings, user):
    settings.GOOGLE_OAUTH_ALLOWED_CLIENT_IDS = [CLIENT_ID]

    response = signin_with_claims(client, google_claims(sub=None))

    assert response.status_code == 401
    assert not GoogleIdentity.objects.exists()


@pytest.mark.django_db
def test_google_signin_first_time_login_links_identity_to_matching_account(
    client, settings, user
):
    settings.GOOGLE_OAUTH_ALLOWED_CLIENT_IDS = [CLIENT_ID]

    response = signin_with_claims(client, google_claims(sub='google-sub-1'))

    assert response.status_code == 200
    identity = GoogleIdentity.objects.get(google_sub='google-sub-1')
    assert identity.user == user


@pytest.mark.django_db
def test_google_signin_previously_linked_identity_authenticates_after_email_change(
    client, settings, user
):
    settings.GOOGLE_OAUTH_ALLOWED_CLIENT_IDS = [CLIENT_ID]
    GoogleIdentity.objects.create(user=user, google_sub='google-sub-1')

    response = signin_with_claims(
        client, google_claims(sub='google-sub-1', email='ada-new-address@example.com')
    )

    assert response.status_code == 200
    assert response.data['token'] == Token.objects.get(user=user).key


@pytest.mark.django_db
def test_google_signin_rejects_embargoed_mapped_account(client, settings):
    settings.GOOGLE_OAUTH_ALLOWED_CLIENT_IDS = [CLIENT_ID]
    account = create_account(country='India')

    response = signin_with_claims(client, google_claims(email=account.email))

    assert response.status_code == 401


@pytest.mark.django_db
def test_google_signin_does_not_link_identity_on_a_rejected_embargoed_first_login(
    client, settings
):
    settings.GOOGLE_OAUTH_ALLOWED_CLIENT_IDS = [CLIENT_ID]
    account = create_account(country='India')

    signin_with_claims(client, google_claims(email=account.email, sub='google-sub-embargoed'))

    assert not GoogleIdentity.objects.filter(google_sub='google-sub-embargoed').exists()


@pytest.mark.django_db
def test_google_signin_succeeds_and_issues_the_existing_token(client, settings, user):
    settings.GOOGLE_OAUTH_ALLOWED_CLIENT_IDS = [CLIENT_ID]

    response = signin_with_claims(client, google_claims())

    assert response.status_code == 200
    assert response.data['token'] == Token.objects.get(user=user).key


@pytest.mark.django_db
def test_google_signin_recovers_from_concurrent_identity_creation_race(client, settings, user):
    settings.GOOGLE_OAUTH_ALLOWED_CLIENT_IDS = [CLIENT_ID]

    def losing_create(user, google_sub):
        # Simulates a concurrent request's create() for the same sub committing first.
        GoogleIdentity(user=user, google_sub=google_sub).save()
        raise IntegrityError('duplicate google_sub')

    with patch('api.views.GoogleIdentity.objects.create', side_effect=losing_create):
        response = signin_with_claims(client, google_claims(sub='google-sub-race'))

    assert response.status_code == 200
    assert response.data['token'] == Token.objects.get(user=user).key
    assert GoogleIdentity.objects.filter(google_sub='google-sub-race').count() == 1


@pytest.mark.django_db
def test_google_signin_response_shape_is_token_only(client, settings, user):
    settings.GOOGLE_OAUTH_ALLOWED_CLIENT_IDS = [CLIENT_ID]

    response = signin_with_claims(client, google_claims())

    assert set(response.data.keys()) == {'token'}
