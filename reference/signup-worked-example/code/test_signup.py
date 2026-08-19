"""Signup conformance tests.

Each test names the requirement it verifies. Written from specs/001-user-signup/spec.md,
after the implementation existed, and deliberately without reading the serializer first --
a test derived from the code asserts what the code does, not what was asked for.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()

VALID = {"username": "ada", "email": "ada@example.com", "password": "correct-horse"}


@pytest.fixture
def url():
    return reverse("signup")


@pytest.mark.django_db
def test_fr001_accepts_username_email_and_password(client, url):
    response = client.post(url, VALID, content_type="application/json")
    assert 200 <= response.status_code < 300


@pytest.mark.django_db
@pytest.mark.parametrize("field", ["username", "email", "password"])
def test_fr002_fr003_fr004_missing_required_field_is_rejected(client, url, field):
    body = {k: v for k, v in VALID.items() if k != field}
    response = client.post(url, body, content_type="application/json")
    assert 400 <= response.status_code < 500
    assert field in response.json()


@pytest.mark.django_db
@pytest.mark.parametrize("field", ["username", "email", "password"])
def test_fr002_fr003_fr004_empty_required_field_is_rejected(client, url, field):
    body = dict(VALID, **{field: ""})
    response = client.post(url, body, content_type="application/json")
    assert 400 <= response.status_code < 500
    assert field in response.json()


@pytest.mark.django_db
def test_fr005_malformed_email_is_rejected(client, url):
    body = dict(VALID, email="not-an-email")
    response = client.post(url, body, content_type="application/json")
    assert 400 <= response.status_code < 500
    assert "email" in response.json()


@pytest.mark.django_db
def test_fr006_duplicate_username_is_rejected(client, url):
    User.objects.create_user(username="ada", email="other@example.com", password="whatever8")
    response = client.post(url, VALID, content_type="application/json")
    assert 400 <= response.status_code < 500
    assert "username" in response.json()


@pytest.mark.django_db
def test_fr007_duplicate_email_is_rejected(client, url):
    User.objects.create_user(username="other", email="ada@example.com", password="whatever8")
    response = client.post(url, VALID, content_type="application/json")
    assert 400 <= response.status_code < 500
    assert "email" in response.json()


@pytest.mark.django_db
def test_fr008_password_shorter_than_minimum_is_rejected(client, url):
    body = dict(VALID, password="short")
    response = client.post(url, body, content_type="application/json")
    assert 400 <= response.status_code < 500
    assert "password" in response.json()


@pytest.mark.django_db
def test_fr008_password_at_the_minimum_is_accepted(client, url):
    body = dict(VALID, password="12345678")
    response = client.post(url, body, content_type="application/json")
    assert 200 <= response.status_code < 300


@pytest.mark.django_db
def test_fr009_valid_submission_creates_exactly_one_account(client, url):
    before = User.objects.count()
    client.post(url, VALID, content_type="application/json")
    assert User.objects.count() == before + 1


@pytest.mark.django_db
def test_fr010_password_is_not_recoverable_from_storage(client, url):
    client.post(url, VALID, content_type="application/json")
    stored = User.objects.get(username="ada").password
    assert stored != VALID["password"]
    assert VALID["password"] not in stored


@pytest.mark.django_db
def test_fr011_password_never_appears_in_a_response(client, url):
    response = client.post(url, VALID, content_type="application/json")
    assert VALID["password"] not in response.content.decode()
    assert "password" not in response.json()


@pytest.mark.django_db
def test_fr012_rejection_identifies_the_offending_field(client, url):
    body = dict(VALID, email="not-an-email")
    response = client.post(url, body, content_type="application/json")
    assert list(response.json().keys()) == ["email"]


@pytest.mark.django_db
def test_fr013_success_and_rejection_differ_by_status(client, url):
    ok = client.post(url, VALID, content_type="application/json")
    bad = client.post(url, dict(VALID, email="nope"), content_type="application/json")
    assert ok.status_code != bad.status_code


@pytest.mark.django_db
def test_fr014_email_uniqueness_is_case_insensitive(client, url):
    User.objects.create_user(username="other", email="ADA@example.com", password="whatever8")
    response = client.post(url, VALID, content_type="application/json")
    assert 400 <= response.status_code < 500
    assert "email" in response.json()


@pytest.mark.django_db
def test_fr015_successful_signup_returns_201(client, url):
    response = client.post(url, VALID, content_type="application/json")
    assert response.status_code == 201
