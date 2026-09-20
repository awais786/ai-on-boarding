import re
import uuid

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from rest_framework import serializers

from embargo.rules import is_blocked, record_account_country

from .models import Membership, Organization

PASSWORD_MIN_LENGTH = 8
USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 30
USERNAME_RE = re.compile(r'^[A-Za-z0-9_]+$')
ORGANIZATION_MAX_LENGTH = 50

# One message for an unknown, inactive, code-less or wrongly-coded organization, so the
# response cannot be used to discover which organizations exist.
JOIN_REFUSED_MESSAGE = 'That organization and join code do not match.'


def validate_password_strength(value):
    if (
        len(value) < PASSWORD_MIN_LENGTH
        or not re.search(r'[A-Za-z]', value)
        or not re.search(r'\d', value)
    ):
        raise serializers.ValidationError(
            f'Must be at least {PASSWORD_MIN_LENGTH} characters and contain a letter and a digit.'
        )


def validate_username_format(value):
    if not USERNAME_RE.fullmatch(value):
        raise serializers.ValidationError(
            'Must contain only letters, digits, or underscores.'
        )


class SignupSerializer(serializers.Serializer):
    organization = serializers.CharField(
        required=True, allow_blank=False, max_length=ORGANIZATION_MAX_LENGTH
    )
    join_code = serializers.CharField(required=True, allow_blank=False, write_only=True)
    email = serializers.EmailField(required=True, allow_blank=False)
    username = serializers.CharField(
        required=True,
        allow_blank=False,
        min_length=USERNAME_MIN_LENGTH,
        max_length=USERNAME_MAX_LENGTH,
        validators=[validate_username_format],
    )
    password = serializers.CharField(
        required=True, allow_blank=False, write_only=True, validators=[validate_password_strength]
    )
    country = serializers.CharField(required=True, allow_blank=False, max_length=100)

    def validate_email(self, value):
        return value.lower()

    def validate_username(self, value):
        return value.lower()

    def validate_country(self, value):
        if is_blocked(value):
            raise serializers.ValidationError('Signups from this country are not allowed.')
        return value

    def validate(self, attrs):
        # The organization is settled before anything that could confirm it exists:
        # a duplicate-email error would otherwise be an oracle for "this organization
        # is real, and this address is in it".
        organization = Organization.active_by_slug(attrs['organization'])
        if organization is None or not organization.accepts_join_code(attrs['join_code']):
            raise serializers.ValidationError({'join_code': [JOIN_REFUSED_MESSAGE]})
        members = Membership.objects.for_organization(organization)
        errors = {}
        if members.filter(email=attrs['email']).exists():
            errors['email'] = ['An account with this email already exists.']
        if members.filter(username=attrs['username']).exists():
            errors['username'] = ['An account with this username already exists.']
        if errors:
            raise serializers.ValidationError(errors)
        attrs['organization'] = organization
        return attrs

    def create(self, validated_data):
        organization = validated_data['organization']
        email = validated_data['email']
        username = validated_data['username']
        try:
            with transaction.atomic():
                # User.username is globally unique but a handle is only unique per
                # organization, so the auth row gets an opaque value (design.md, D2).
                user = User.objects.create_user(
                    username=uuid.uuid4().hex, email=email, password=validated_data['password']
                )
                Membership.objects.create(
                    user=user, organization=organization, email=email, username=username
                )
                record_account_country(user, validated_data['country'])
                return user
        except IntegrityError:
            # Decided by asking the database rather than parsing the error text, which
            # differs between SQLite and Postgres and can echo the submitted value.
            members = Membership.objects.for_organization(organization)
            if members.filter(username=username).exists():
                field = 'username'
            elif members.filter(email=email).exists():
                field = 'email'
            else:
                raise
            raise serializers.ValidationError(
                {field: [f'An account with this {field} already exists.']}
            )


class AccountSerializer(serializers.Serializer):
    email = serializers.CharField(source='membership.email')
    username = serializers.CharField(source='membership.username')


class SigninSerializer(serializers.Serializer):
    organization = serializers.CharField(
        required=True, allow_blank=False, max_length=ORGANIZATION_MAX_LENGTH
    )
    email_or_username = serializers.CharField(required=True, allow_blank=False, max_length=255)
    password = serializers.CharField(required=True, allow_blank=False, write_only=True)


class PasswordResetRequestSerializer(serializers.Serializer):
    organization = serializers.CharField(
        required=True, allow_blank=False, max_length=ORGANIZATION_MAX_LENGTH
    )
    email = serializers.EmailField(required=True, allow_blank=False)


class PasswordResetConfirmSerializer(serializers.Serializer):
    code = serializers.CharField(required=True, allow_blank=False)
    password = serializers.CharField(
        required=True, allow_blank=False, write_only=True, validators=[validate_password_strength]
    )


class TokenSerializer(serializers.Serializer):
    token = serializers.CharField()


class UserAccountSerializer(serializers.ModelSerializer):
    """The user-list representation. Neither `id` nor `email` is exposed here -
    AdminChangePasswordView's URL is keyed on username, not id, and email is PII an
    authenticated caller listing users has no need to see."""

    username = serializers.CharField(source='membership.username')
    country = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['username', 'country', 'date_joined']

    def get_country(self, obj):
        account_country = getattr(obj, 'accountcountry', None)
        return account_country.country if account_country else None


class AdminChangePasswordSerializer(serializers.Serializer):
    password = serializers.CharField(
        required=True, allow_blank=False, write_only=True, validators=[validate_password_strength]
    )


class SelfChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(required=True, allow_blank=False, write_only=True)
    new_password = serializers.CharField(
        required=True, allow_blank=False, write_only=True, validators=[validate_password_strength]
    )


class GoogleAuthSerializer(serializers.Serializer):
    access_token = serializers.CharField(required=True, allow_blank=False, write_only=True)
