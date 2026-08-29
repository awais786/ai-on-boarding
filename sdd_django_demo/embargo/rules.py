from .models import AccountCountry, BlockedCountry


def is_blocked(country):
    return BlockedCountry.objects.filter(country=country.lower()).exists()


def is_user_embargoed(user):
    account_country = AccountCountry.objects.filter(user=user).first()
    return account_country is not None and is_blocked(account_country.country)


def record_account_country(user, country):
    AccountCountry.objects.update_or_create(user=user, defaults={'country': country})
