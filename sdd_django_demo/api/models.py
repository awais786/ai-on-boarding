import hashlib
import hmac
import secrets
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from django.db import IntegrityError, models, transaction
from django.utils import timezone

from .tenancy import TenantQuerySet

RESET_CODE_TTL = timedelta(minutes=30)
RESET_CODE_BYTES = 32
JOIN_CODE_BYTES = 24
SLUG_PATTERN = r'^[a-z0-9-]+$'


def hash_reset_code(code):
    return hashlib.sha256(code.encode()).hexdigest()


class Organization(models.Model):
    name = models.CharField(max_length=200)
    slug = models.CharField(
        max_length=50,
        unique=True,
        validators=[RegexValidator(SLUG_PATTERN, 'Use lowercase letters, digits and hyphens.')],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    # SHA-256 of the join code; blank means signup into this organization is closed.
    join_code_digest = models.CharField(max_length=64, blank=True, default='')

    class Meta:
        constraints = [
            # The validator above only runs through forms; this keeps a slug lowercase
            # (so uniqueness is effectively case-insensitive) whatever wrote the row.
            models.CheckConstraint(
                condition=models.Q(slug__regex=SLUG_PATTERN), name='organization_slug_format'
            )
        ]

    def __str__(self):
        return self.slug

    @classmethod
    def active_by_slug(cls, slug):
        """The active organization with this slug, or None. Case-insensitive."""
        if not isinstance(slug, str):
            return None
        return cls.objects.filter(slug=slug.strip().lower(), is_active=True).first()

    def issue_join_code(self):
        """Replace the join code, returning the new one. It is not recoverable afterwards."""
        code = secrets.token_urlsafe(JOIN_CODE_BYTES)
        self.join_code_digest = hash_join_code(code)
        self.save(update_fields=['join_code_digest', 'updated_at'])
        return code

    def accepts_join_code(self, code):
        if not self.join_code_digest or not code:
            return False
        return hmac.compare_digest(hash_join_code(code), self.join_code_digest)


def hash_join_code(code):
    # Unsalted and fast on purpose: the code is 192 random bits, so there is nothing to
    # brute-force. The same reasoning as hash_reset_code above.
    return hashlib.sha256(code.encode()).hexdigest()


class Membership(models.Model):
    """Which organization an account belongs to, and the identity it holds there.

    email and username live here, not on User, because auth_user.username is globally
    unique and these must be unique per organization only (design.md, D1/D2).
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='membership')
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name='memberships'
    )
    email = models.CharField(max_length=254, blank=True)
    username = models.CharField(max_length=150)

    objects = TenantQuerySet.as_manager()

    class Meta:
        constraints = [
            # Constraint names contain "email"/"username" so a violation can be told apart.
            # Blank emails (accounts made outside signup) are exempt from uniqueness.
            models.UniqueConstraint(
                fields=['organization', 'email'],
                condition=~models.Q(email=''),
                name='membership_unique_org_email',
            ),
            models.UniqueConstraint(
                fields=['organization', 'username'], name='membership_unique_org_username'
            ),
        ]


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


class SigninAttempt(models.Model):
    # "<organization slug>|<identifier>": lockout is counted per organization.
    email_or_username = models.CharField(max_length=320, unique=True)
    failed_count = models.PositiveIntegerField(default=0)
    # When the current run of consecutive failures began. Reset only when a failure
    # lands after the window has fully elapsed, so a burst of failures each less
    # than FAILURE_WINDOW apart than its predecessor - but spanning longer than
    # FAILURE_WINDOW overall - does not falsely trigger lockout. Distinct from
    # last_failed_at (below), which tracks the most recent failure and drives
    # lockout *expiry* instead.
    window_started_at = models.DateTimeField(null=True, blank=True)
    last_failed_at = models.DateTimeField(null=True, blank=True)
