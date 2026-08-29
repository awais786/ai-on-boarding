import pytest
from django.contrib.auth.models import User

from embargo.models import AccountCountry, BlockedCountry
from embargo.rules import is_blocked, record_account_country


@pytest.mark.django_db
def test_unlisted_country_is_allowed():
    assert is_blocked('Erewhon') is False


@pytest.mark.django_db
def test_listed_country_is_blocked():
    BlockedCountry.objects.create(country='Erewhon')

    assert is_blocked('Erewhon') is True


@pytest.mark.django_db
def test_country_matched_case_insensitively():
    BlockedCountry.objects.create(country='Erewhon')

    assert is_blocked('erewhon') is True
    assert is_blocked('EREWHON') is True


@pytest.mark.django_db
def test_later_addition_takes_effect():
    assert is_blocked('Erewhon') is False

    BlockedCountry.objects.create(country='Erewhon')

    assert is_blocked('Erewhon') is True


@pytest.mark.django_db
def test_later_removal_takes_effect():
    entry = BlockedCountry.objects.create(country='Erewhon')
    assert is_blocked('Erewhon') is True

    entry.delete()

    assert is_blocked('Erewhon') is False


@pytest.mark.django_db
def test_blocked_country_is_stored_lowercase():
    entry = BlockedCountry.objects.create(country='Erewhon')

    entry.refresh_from_db()
    assert entry.country == 'erewhon'


@pytest.mark.django_db
def test_account_country_is_stored_lowercase():
    user = User.objects.create_user(username='ada@example.com', email='ada@example.com')

    record_account_country(user, 'Erewhon')

    assert AccountCountry.objects.get(user=user).country == 'erewhon'
