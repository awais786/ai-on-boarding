from django.contrib import admin

from .models import AccountCountry, BlockedCountry

admin.site.register(BlockedCountry)
admin.site.register(AccountCountry)
