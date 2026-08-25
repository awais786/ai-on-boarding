import hashlib
import secrets
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import IntegrityError, models, transaction
from django.utils import timezone

RESET_CODE_TTL = timedelta(minutes=30)
RESET_CODE_BYTES = 32


def hash_reset_code(code):
    return hashlib.sha256(code.encode()).hexdigest()


class PasswordResetCode(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='password_reset_codes'
    )
    code_digest = models.CharField(max_length=64, unique=True)
    issued_at = models.DateTimeField(default=timezone.now)
    usable = models.BooleanField(default=True)

    class Meta:
        constraints = [
            # "Supersede an earlier unused code" as a database invariant rather than
            # a promise the application remembers to keep. Two concurrent requests
            # cannot both leave a usable row behind: the loser raises IntegrityError
            # and retries, the same shape signup uses for its duplicate-email race.
            models.UniqueConstraint(
                fields=['user'],
                condition=models.Q(usable=True),
                name='one_usable_reset_code_per_user',
            )
        ]

    @classmethod
    def issue_for(cls, user):
        try:
            return cls._issue(user)
        except IntegrityError:
            # A concurrent request took the one usable row the partial unique index
            # allows. Retrying is enough: the winner's row is now the earlier code
            # this attempt supersedes. A second failure is not a race and propagates.
            return cls._issue(user)

    @classmethod
    def _issue(cls, user):
        with transaction.atomic():
            cls.objects.filter(user=user, usable=True).update(usable=False)
            code = secrets.token_urlsafe(RESET_CODE_BYTES)
            cls.objects.create(user=user, code_digest=hash_reset_code(code))
            return code

    @classmethod
    def resolve(cls, code):
        if not code:
            return None
        record = cls.objects.filter(code_digest=hash_reset_code(code), usable=True).first()
        if record is None or record.is_expired():
            return None
        return record

    def is_expired(self):
        return timezone.now() - self.issued_at > RESET_CODE_TTL

    def claim(self):
        """Consume this code, returning False if someone else already did.

        A conditional UPDATE rather than a read-then-write: "Retire a reset code
        once it is used" then holds even when two completions race, without needing
        row locks the SQLite backend does not have.
        """
        return type(self).objects.filter(pk=self.pk, usable=True).update(usable=False) == 1
