from django.conf import settings
from django.db import models


class BlockedCountry(models.Model):
    country = models.CharField(max_length=100, unique=True)


class AccountCountry(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    country = models.CharField(max_length=100)
