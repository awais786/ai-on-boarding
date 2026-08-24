from django.db import models


class SigninAttempt(models.Model):
    email_or_username = models.CharField(max_length=255, unique=True)
    failed_count = models.PositiveIntegerField(default=0)
    last_failed_at = models.DateTimeField(null=True, blank=True)
