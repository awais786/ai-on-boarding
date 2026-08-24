import pytest

from embargo.models import BlockedCountry
from embargo.rules import is_blocked


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
