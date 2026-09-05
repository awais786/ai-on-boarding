import pytest
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token


def create_staff(email='admin@example.com', password='adminpass1'):
    return User.objects.create_user(
        username='admin', email=email, password=password, is_staff=True
    )


def create_regular(email='ada@example.com', password='lovelace1'):
    return User.objects.create_user(username='ada', email=email, password=password)


def auth(client, user):
    token, _ = Token.objects.get_or_create(user=user)
    client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')


@pytest.mark.django_db
def test_list_users_rejects_unauthenticated_request(client):
    create_staff()

    response = client.get('/api/users/')

    assert response.status_code == 401


@pytest.mark.django_db
def test_list_users_rejects_authenticated_non_staff(client):
    regular = create_regular()
    auth(client, regular)

    response = client.get('/api/users/')

    assert response.status_code == 403


@pytest.mark.django_db
def test_list_users_accepts_staff_request(client):
    staff = create_staff()
    auth(client, staff)

    response = client.get('/api/users/')

    assert response.status_code == 200


@pytest.mark.django_db
def test_list_users_accepts_staff_session_login(client):
    staff = create_staff()
    client.login(username=staff.username, password='adminpass1')

    response = client.get('/api/users/')

    assert response.status_code == 200


@pytest.mark.django_db
def test_list_users_response_contains_only_expected_fields(client):
    staff = create_staff()
    create_regular()
    auth(client, staff)

    response = client.get('/api/users/')

    assert response.status_code == 200
    for entry in response.data['results']:
        assert set(entry.keys()) == {'id', 'email', 'date_joined'}


@pytest.mark.django_db
def test_list_users_paginates_large_user_set(client):
    staff = create_staff()
    for i in range(25):
        User.objects.create_user(
            username=f'user{i}', email=f'user{i}@example.com', password='pw12345'
        )
    auth(client, staff)

    response = client.get('/api/users/')

    assert response.status_code == 200
    assert len(response.data['results']) == 20
    assert response.data['next'] is not None


@pytest.mark.django_db
def test_list_users_empty_set_returns_success(client):
    staff = create_staff()
    auth(client, staff)

    response = client.get('/api/users/')

    assert response.status_code == 200
    assert [entry['id'] for entry in response.data['results']] == [staff.id]


@pytest.mark.django_db
def test_list_users_reflects_newly_signed_up_account_across_all_pages(client):
    staff = create_staff()
    auth(client, staff)
    new_user = create_regular()

    seen_ids = []
    url = '/api/users/'
    while url:
        response = client.get(url)
        assert response.status_code == 200
        seen_ids.extend(entry['id'] for entry in response.data['results'])
        url = response.data['next']
        if url:
            url = url.replace('http://testserver', '')

    assert seen_ids.count(new_user.id) == 1
