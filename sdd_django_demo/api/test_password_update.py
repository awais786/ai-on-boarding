import pytest
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token


def create_staff(email='admin@example.com', password='adminpass1'):
    return User.objects.create_user(
        username='admin', email=email, password=password, is_staff=True
    )


def create_regular(username='ada', email='ada@example.com', password='lovelace1'):
    return User.objects.create_user(username=username, email=email, password=password)


def auth(client, user):
    token, _ = Token.objects.get_or_create(user=user)
    client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
    return token


def password_update_url(target):
    return f'/api/users/{target.username}/update-password/'


@pytest.mark.django_db
def test_password_update_rejects_unauthenticated_request(client):
    regular = create_regular()

    response = client.patch(
        password_update_url(regular),
        {'current_password': 'lovelace1', 'new_password': 'newpassword1'},
        content_type='application/json',
    )

    assert response.status_code == 401


@pytest.mark.django_db
def test_password_update_rejects_nonexistent_target(client):
    staff = create_staff()
    auth(client, staff)

    response = client.patch(
        '/api/users/no-such-user/update-password/',
        {'new_password': 'newpassword1'},
        content_type='application/json',
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_password_update_matches_username_case_insensitively(client):
    staff = create_staff()
    regular = create_regular(username='ada')
    auth(client, staff)

    response = client.patch(
        '/api/users/ADA/update-password/',
        {'new_password': 'newpassword1'},
        content_type='application/json',
    )

    assert response.status_code == 200
    regular.refresh_from_db()
    assert regular.check_password('newpassword1')


@pytest.mark.django_db
def test_password_update_rejects_non_staff_targeting_another_account(client):
    regular = create_regular()
    other = create_regular(username='grace', email='other@example.com', password='otherpass1')
    auth(client, regular)

    response = client.patch(
        password_update_url(other),
        {'new_password': 'newpassword1'},
        content_type='application/json',
    )

    assert response.status_code == 403
    other.refresh_from_db()
    assert other.check_password('otherpass1')


@pytest.mark.django_db
def test_password_update_allows_staff_to_target_another_account(client):
    staff = create_staff()
    regular = create_regular()
    auth(client, staff)

    response = client.patch(
        password_update_url(regular),
        {'new_password': 'newpassword1'},
        content_type='application/json',
    )

    assert response.status_code == 200


@pytest.mark.django_db
def test_password_update_self_service_requires_current_password_field(client):
    regular = create_regular()
    auth(client, regular)

    response = client.patch(
        password_update_url(regular),
        {'new_password': 'newpassword1'},
        content_type='application/json',
    )

    assert response.status_code == 400
    assert 'current_password' in response.data


@pytest.mark.django_db
def test_password_update_self_service_rejects_incorrect_current_password(client):
    regular = create_regular()
    auth(client, regular)

    response = client.patch(
        password_update_url(regular),
        {'current_password': 'wrongpassword1', 'new_password': 'newpassword1'},
        content_type='application/json',
    )

    assert response.status_code == 400
    regular.refresh_from_db()
    assert regular.check_password('lovelace1')


@pytest.mark.django_db
def test_password_update_self_service_succeeds_with_correct_current_password(client):
    regular = create_regular()
    auth(client, regular)

    response = client.patch(
        password_update_url(regular),
        {'current_password': 'lovelace1', 'new_password': 'newpassword1'},
        content_type='application/json',
    )

    assert response.status_code == 200


@pytest.mark.django_db
def test_password_update_staff_targeting_own_account_requires_current_password(client):
    staff = create_staff()
    auth(client, staff)

    response = client.patch(
        password_update_url(staff),
        {'new_password': 'newpassword1'},
        content_type='application/json',
    )

    assert response.status_code == 400
    assert 'current_password' in response.data
    staff.refresh_from_db()
    assert staff.check_password('adminpass1')


@pytest.mark.django_db
def test_password_update_staff_targeting_own_account_succeeds_with_correct_current_password(
    client,
):
    staff = create_staff()
    auth(client, staff)

    response = client.patch(
        password_update_url(staff),
        {'current_password': 'adminpass1', 'new_password': 'newpassword1'},
        content_type='application/json',
    )

    assert response.status_code == 200
    staff.refresh_from_db()
    assert staff.check_password('newpassword1')


@pytest.mark.django_db
def test_password_update_admin_issued_update_does_not_require_current_password(client):
    staff = create_staff()
    regular = create_regular()
    auth(client, staff)

    response = client.patch(
        password_update_url(regular),
        {'new_password': 'newpassword1'},
        content_type='application/json',
    )

    assert response.status_code == 200
    regular.refresh_from_db()
    assert regular.check_password('newpassword1')


@pytest.mark.django_db
def test_password_update_rejects_missing_new_password(client):
    regular = create_regular()
    auth(client, regular)

    response = client.patch(
        password_update_url(regular),
        {'current_password': 'lovelace1'},
        content_type='application/json',
    )

    assert response.status_code == 400
    assert 'new_password' in response.data


@pytest.mark.django_db
def test_password_update_rejects_weak_new_password(client):
    regular = create_regular()
    auth(client, regular)

    response = client.patch(
        password_update_url(regular),
        {'current_password': 'lovelace1', 'new_password': 'weak'},
        content_type='application/json',
    )

    assert response.status_code == 400
    assert 'new_password' in response.data
    regular.refresh_from_db()
    assert regular.check_password('lovelace1')


@pytest.mark.django_db
def test_password_update_success_response_contains_no_password(client):
    regular = create_regular()
    auth(client, regular)

    response = client.patch(
        password_update_url(regular),
        {'current_password': 'lovelace1', 'new_password': 'newpassword1'},
        content_type='application/json',
    )

    assert response.status_code == 200
    body = str(response.data)
    assert 'lovelace1' not in body
    assert 'newpassword1' not in body


@pytest.mark.django_db
def test_password_update_rejected_response_contains_no_password(client):
    regular = create_regular()
    auth(client, regular)

    response = client.patch(
        password_update_url(regular),
        {'current_password': 'wrongpassword1', 'new_password': 'newpassword1'},
        content_type='application/json',
    )

    assert response.status_code == 400
    body = str(response.data)
    assert 'wrongpassword1' not in body
    assert 'newpassword1' not in body


@pytest.mark.django_db
def test_password_update_new_password_works_old_does_not(client):
    regular = create_regular()
    auth(client, regular)

    client.patch(
        password_update_url(regular),
        {'current_password': 'lovelace1', 'new_password': 'newpassword1'},
        content_type='application/json',
    )

    regular.refresh_from_db()
    assert regular.check_password('newpassword1')
    assert not regular.check_password('lovelace1')


@pytest.mark.django_db
def test_password_update_invalidates_existing_tokens_on_self_update(client):
    regular = create_regular()
    pre_existing_token = auth(client, regular)

    client.patch(
        password_update_url(regular),
        {'current_password': 'lovelace1', 'new_password': 'newpassword1'},
        content_type='application/json',
    )

    assert not Token.objects.filter(key=pre_existing_token.key).exists()


@pytest.mark.django_db
def test_password_update_invalidates_target_tokens_on_admin_update_but_not_admins_own(client):
    staff = create_staff()
    regular = create_regular()
    admin_token = auth(client, staff)
    target_token, _ = Token.objects.get_or_create(user=regular)

    response = client.patch(
        password_update_url(regular),
        {'new_password': 'newpassword1'},
        content_type='application/json',
    )

    assert response.status_code == 200
    assert not Token.objects.filter(key=target_token.key).exists()
    assert Token.objects.filter(key=admin_token.key).exists()
