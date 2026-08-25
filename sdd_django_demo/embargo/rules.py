from .models import AccountCountry, BlockedCountry


def is_blocked(country):
    return BlockedCountry.objects.filter(country=country.lower()).exists()


def record_account_country(user, country):
    AccountCountry.objects.update_or_create(user=user, defaults={'country': country})
