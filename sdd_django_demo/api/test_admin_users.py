import pytest
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from embargo.rules import record_account_country


@pytest.fixture
def client():
    return APIClient()


def create_account(username, email, password='lovelace1', country=None, is_staff=False):
    account = User.objects.create_user(
        username=username, email=email, password=password, is_staff=is_staff
    )
    if country is not None:
        record_account_country(account, country)
    return account


def auth(client, user):
    token, _ = Token.objects.get_or_create(user=user)
    client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
    return token


@pytest.mark.django_db
def test_user_list_requires_authentication(client):
    response = client.get('/api/users/')

    assert response.status_code == 401


@pytest.mark.django_db
def test_user_list_returns_all_signup_users(client):
    ada = create_account('ada', 'ada@example.com', country='Pakistan')
    grace = create_account('grace', 'grace@example.com', country='India')
    auth(client, ada)

    response = client.get('/api/users/')

    assert response.status_code == 200
    usernames = {row['username'] for row in response.data}
    assert usernames == {'ada', 'grace'}


@pytest.mark.django_db
def test_user_list_includes_country(client):
    ada = create_account('ada', 'ada@example.com', country='Pakistan')
    auth(client, ada)

    response = client.get('/api/users/')

    row = next(row for row in response.data if row['username'] == 'ada')
    assert row['country'] == 'pakistan'


@pytest.mark.django_db
def test_user_list_user_without_country_returns_null(client):
    admin = create_account('admin', 'admin@example.com', is_staff=True)
    auth(client, admin)

    response = client.get('/api/users/')

    row = next(row for row in response.data if row['username'] == 'admin')
    assert row['country'] is None


@pytest.mark.django_db
def test_user_list_filter_by_country(client):
    ada = create_account('ada', 'ada@example.com', country='Pakistan')
    create_account('grace', 'grace@example.com', country='India')
    auth(client, ada)

    response = client.get('/api/users/', {'country': 'Pakistan'})

    assert response.status_code == 200
    assert {row['username'] for row in response.data} == {'ada'}


@pytest.mark.django_db
def test_user_list_filter_by_country_is_case_insensitive(client):
    ada = create_account('ada', 'ada@example.com', country='Pakistan')
    auth(client, ada)

    response = client.get('/api/users/', {'country': 'PAKISTAN'})

    assert {row['username'] for row in response.data} == {'ada'}


@pytest.mark.django_db
def test_user_list_filter_by_unmatched_country_returns_empty(client):
    ada = create_account('ada', 'ada@example.com', country='Pakistan')
    auth(client, ada)

    response = client.get('/api/users/', {'country': 'Freedonia'})

    assert response.data == []


@pytest.mark.django_db
def test_user_list_response_never_contains_password(client):
    ada = create_account('ada', 'ada@example.com', country='Pakistan')
    auth(client, ada)

    response = client.get('/api/users/')

    assert 'password' not in response.content.decode()


@pytest.mark.django_db
def test_admin_change_password_requires_authentication(client):
    target = create_account('ada', 'ada@example.com')

    response = client.post(
        f'/api/users/{target.pk}/change-password/', {'password': 'newpass1'}, format='json'
    )

    assert response.status_code == 401


@pytest.mark.django_db
def test_admin_change_password_rejects_non_admin(client):
    target = create_account('ada', 'ada@example.com')
    caller = create_account('grace', 'grace@example.com', is_staff=False)
    auth(client, caller)

    response = client.post(
        f'/api/users/{target.pk}/change-password/', {'password': 'newpass1'}, format='json'
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_admin_change_password_succeeds_for_admin(client):
    target = create_account('ada', 'ada@example.com', password='oldpass1')
    admin = create_account('admin', 'admin@example.com', is_staff=True)
    auth(client, admin)

    response = client.post(
        f'/api/users/{target.pk}/change-password/', {'password': 'newpass1'}, format='json'
    )

    assert response.status_code == 200
    target.refresh_from_db()
    assert target.check_password('newpass1')
    assert not target.check_password('oldpass1')


@pytest.mark.django_db
def test_admin_change_password_revokes_existing_token(client):
    target = create_account('ada', 'ada@example.com', password='oldpass1')
    Token.objects.get_or_create(user=target)
    admin = create_account('admin', 'admin@example.com', is_staff=True)
    auth(client, admin)

    client.post(f'/api/users/{target.pk}/change-password/', {'password': 'newpass1'}, format='json')

    assert not Token.objects.filter(user=target).exists()


@pytest.mark.django_db
def test_admin_change_password_rejects_weak_password(client):
    target = create_account('ada', 'ada@example.com', password='oldpass1')
    admin = create_account('admin', 'admin@example.com', is_staff=True)
    auth(client, admin)

    response = client.post(
        f'/api/users/{target.pk}/change-password/', {'password': 'short'}, format='json'
    )

    assert response.status_code == 400
    target.refresh_from_db()
    assert target.check_password('oldpass1')


@pytest.mark.django_db
def test_admin_change_password_unknown_user_returns_404(client):
    admin = create_account('admin', 'admin@example.com', is_staff=True)
    auth(client, admin)

    response = client.post('/api/users/9999/change-password/', {'password': 'newpass1'}, format='json')

    assert response.status_code == 404


@pytest.mark.django_db
def test_admin_change_password_response_never_contains_password(client):
    target = create_account('ada', 'ada@example.com', password='oldpass1')
    admin = create_account('admin', 'admin@example.com', is_staff=True)
    auth(client, admin)

    response = client.post(
        f'/api/users/{target.pk}/change-password/', {'password': 'newpass1'}, format='json'
    )

    assert 'newpass1' not in response.content.decode()
