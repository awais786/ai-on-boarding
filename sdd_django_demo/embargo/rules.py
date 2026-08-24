from .models import AccountCountry, BlockedCountry


def is_blocked(country):
    return BlockedCountry.objects.filter(country__iexact=country).exists()


def record_account_country(user, country):
    AccountCountry.objects.update_or_create(user=user, defaults={'country': country})
