"""Tests for specs/tenant-isolation/spec.md, written from the spec.

Each requirement and what a test needs to observe to protect it:

- Take the tenant from the credential, never from client input -> naming another
  organization in the body, query string or a header changes nothing.
- Refuse a token whose user is inactive -> a token issued earlier stops working.
- Refuse a token whose organization is inactive -> the same, and it works again once the
  organization is reactivated.
- Refuse a token that has no organization -> an account outside every organization is refused.
- Scope the user list to the caller's organization -> other organizations' users never appear,
  and a filter cannot reach across.
- Scope admin password changes to the caller's organization -> works inside, and a username in
  another organization is a 404 that leaves that user's password and tokens untouched.
- Never reveal another organization through a response -> a cross-organization target and a
  nonexistent one are indistinguishable.
- Refuse a Google sign-in for an inactive organization -> no token, and the response matches
  the one for an unknown address; an address shared across organizations is still refused.
"""

import pytest
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from api.factories import create_member, make_organization
from embargo.rules import record_account_country


def authed(user):
    client = APIClient()
    token, _ = Token.objects.get_or_create(user=user)
    client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
    return client


@pytest.fixture
def acme_admin(db):
    return create_member('acme_admin', 'admin@acme.com', organization='acme', is_staff=True)


@pytest.fixture
def two_organizations(acme_admin):
    """Acme (with admin) and Globex, each holding people the other must never see."""
    acme_user = create_member('alice', 'alice@acme.com', organization='acme')
    globex_admin = create_member(
        'globex_admin', 'admin@globex.com', organization='globex', is_staff=True
    )
    globex_user = create_member('bob', 'bob@globex.com', organization='globex')
    record_account_country(acme_user, 'france')
    record_account_country(globex_user, 'spain')
    return {'acme_user': acme_user, 'globex_admin': globex_admin, 'globex_user': globex_user}


def usernames(response):
    return sorted(row['username'] for row in response.data)


# Requirement: Take the tenant from the credential, never from client input


@pytest.mark.django_db
def test_naming_another_organization_in_a_request_changes_nothing(acme_admin, two_organizations):
    client = authed(acme_admin)
    plain = client.get('/api/users/')

    in_query = client.get('/api/users/', {'organization': 'globex'})
    in_header = client.get('/api/users/', HTTP_X_ORGANIZATION='globex')
    in_body = client.generic(
        'GET', '/api/users/', '{"organization": "globex"}', content_type='application/json'
    )

    assert usernames(plain) == ['acme_admin', 'alice']
    for response in (in_query, in_header, in_body):
        assert response.status_code == 200
        assert usernames(response) == usernames(plain)


@pytest.mark.django_db
def test_a_django_admin_session_cannot_reach_tenant_endpoints(acme_admin):
    client = APIClient()
    client.force_login(acme_admin)

    assert client.get('/api/users/').status_code in (401, 403)


# Requirement: Refuse a token whose user is inactive


@pytest.mark.django_db
def test_a_token_issued_before_the_user_was_deactivated_stops_working(acme_admin):
    client = authed(acme_admin)
    assert client.get('/api/users/').status_code == 200

    acme_admin.is_active = False
    acme_admin.save()

    assert client.get('/api/users/').status_code == 401


# Requirement: Refuse a token whose organization is inactive


@pytest.mark.django_db
def test_a_token_stops_working_when_its_organization_is_deactivated_and_resumes_on_reactivation(
    acme_admin,
):
    client = authed(acme_admin)
    organization = make_organization('acme')

    organization.is_active = False
    organization.save()
    assert client.get('/api/users/').status_code == 401

    organization.is_active = True
    organization.save()
    assert client.get('/api/users/').status_code == 200


@pytest.mark.django_db
def test_deactivating_one_organization_does_not_affect_another(acme_admin, two_organizations):
    globex = make_organization('globex')
    globex.is_active = False
    globex.save()

    assert authed(acme_admin).get('/api/users/').status_code == 200
    assert authed(two_organizations['globex_admin']).get('/api/users/').status_code == 401


@pytest.mark.django_db
def test_the_refusal_is_the_same_whichever_check_failed(acme_admin):
    gone = make_organization('gone', is_active=False)
    inactive_org = create_member('x', 'x@inactive.com', organization=gone, is_staff=True)
    unknown = APIClient()
    unknown.credentials(HTTP_AUTHORIZATION='Token nonsense')

    refusals = [authed(inactive_org).get('/api/users/'), unknown.get('/api/users/')]

    assert refusals[0].status_code == refusals[1].status_code == 401
    assert refusals[0].data == refusals[1].data


# Requirement: Refuse a token that has no organization


@pytest.mark.django_db
def test_an_account_outside_every_organization_is_refused():
    operator = User.objects.create_superuser('operator', 'op@example.com', 'operator-pass1')

    assert authed(operator).get('/api/users/').status_code == 401


# Requirement: Scope the user list to the caller's organization


@pytest.mark.django_db
def test_the_user_list_contains_only_the_admins_own_organization(acme_admin, two_organizations):
    response = authed(acme_admin).get('/api/users/')

    assert usernames(response) == ['acme_admin', 'alice']


@pytest.mark.django_db
def test_a_username_filter_cannot_reach_another_organization(acme_admin, two_organizations):
    response = authed(acme_admin).get('/api/users/', {'username': 'bob'})

    assert response.status_code == 200
    assert response.data == []


@pytest.mark.django_db
def test_a_country_filter_cannot_reach_another_organization(acme_admin, two_organizations):
    response = authed(acme_admin).get('/api/users/', {'country': 'spain'})

    assert response.status_code == 200
    assert response.data == []


@pytest.mark.django_db
def test_the_same_username_in_two_organizations_lists_only_the_callers(acme_admin):
    create_member('sam', 'sam@acme.com', organization='acme')
    create_member('sam', 'sam@globex.com', organization='globex')

    response = authed(acme_admin).get('/api/users/', {'username': 'sam'})

    assert len(response.data) == 1


# Requirement: Scope admin password changes to the caller's organization


def change_password(client, username, password='new-password-1'):
    return client.post(
        f'/api/users/{username}/change-password/', {'password': password}, format='json'
    )


@pytest.mark.django_db
def test_an_admin_changes_the_password_of_a_user_in_their_own_organization(
    acme_admin, two_organizations
):
    response = change_password(authed(acme_admin), 'alice')

    assert response.status_code == 200
    assert User.objects.get(pk=two_organizations['acme_user'].pk).check_password('new-password-1')


@pytest.mark.django_db
def test_an_admin_cannot_change_a_password_in_another_organization(acme_admin, two_organizations):
    victim = two_organizations['globex_user']
    victim_token = Token.objects.create(user=victim)

    response = change_password(authed(acme_admin), 'bob')

    assert response.status_code == 404
    victim.refresh_from_db()
    assert victim.check_password('lovelace1')
    assert Token.objects.filter(pk=victim_token.pk).exists()


@pytest.mark.django_db
def test_the_same_username_in_two_organizations_changes_only_the_callers(acme_admin):
    mine = create_member('sam', 'sam@acme.com', organization='acme')
    theirs = create_member('sam', 'sam@globex.com', organization='globex')

    assert change_password(authed(acme_admin), 'sam').status_code == 200

    mine.refresh_from_db()
    theirs.refresh_from_db()
    assert mine.check_password('new-password-1')
    assert theirs.check_password('lovelace1')


# Requirement: Never reveal another organization through a response


@pytest.mark.django_db
def test_another_organizations_user_and_a_nonexistent_one_look_identical(
    acme_admin, two_organizations
):
    client = authed(acme_admin)

    cross = change_password(client, 'bob')
    nowhere = change_password(client, 'nobody_at_all')

    assert cross.status_code == nowhere.status_code == 404
    assert cross.data == nowhere.data


# Requirement: Refuse a Google sign-in for an inactive organization


class FakeTokeninfo:
    status_code = 200

    def __init__(self, email):
        self._email = email

    def json(self):
        return {'email': self._email, 'email_verified': 'true', 'aud': 'client-1', 'hd': ''}


@pytest.fixture
def google(monkeypatch, settings):
    settings.GOOGLE_OAUTH_CLIENT_IDS = ['client-1']
    settings.GOOGLE_ALLOWED_HD = ''

    def sign_in(email):
        monkeypatch.setattr(
            'api.google_auth.requests.get', lambda *a, **k: FakeTokeninfo(email)
        )
        return APIClient().post('/api/auth/google/', {'access_token': 'x'}, format='json')

    return sign_in


@pytest.mark.django_db
def test_google_signin_is_refused_for_an_inactive_organization_like_an_unknown_address(google):
    organization = make_organization('acme')
    create_member('ada', 'ada@example.com', organization=organization)
    organization.is_active = False
    organization.save()

    inactive = google('ada@example.com')
    unknown = google('nobody@example.com')

    assert inactive.status_code == unknown.status_code == 403
    assert inactive.data == unknown.data
    assert 'token' not in inactive.data


@pytest.mark.django_db
def test_google_signin_is_refused_for_an_inactive_user(google):
    create_member('ada', 'ada@example.com', is_active=False)

    assert google('ada@example.com').status_code == 403


@pytest.mark.django_db
def test_google_signin_is_refused_when_the_address_is_in_two_active_organizations(google):
    create_member('ada', 'ada@example.com', organization='acme')
    create_member('ada', 'ada@example.com', organization='globex')

    response = google('ada@example.com')

    assert response.status_code == 403
    assert 'token' not in response.data


@pytest.mark.django_db
def test_a_dormant_duplicate_in_an_inactive_organization_does_not_block_a_live_account(google):
    create_member('ada', 'ada@example.com', organization='acme')
    create_member('ada', 'ada@example.com', organization=make_organization('old', is_active=False))

    assert google('ada@example.com').status_code == 200
