import re

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from rest_framework import serializers

from embargo.rules import is_blocked, record_account_country

PASSWORD_MIN_LENGTH = 8
USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 30
USERNAME_RE = re.compile(r'^[A-Za-z0-9_]+$')


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
        normalised = value.lower()
        if User.objects.filter(email=normalised).exists():
            raise serializers.ValidationError('An account with this email already exists.')
        return normalised

    def validate_username(self, value):
        normalised = value.lower()
        if User.objects.filter(username=normalised).exists():
            raise serializers.ValidationError('An account with this username already exists.')
        return normalised
    def validate_country(self, value):
        if is_blocked(value):
            raise serializers.ValidationError('Signups from this country are not allowed.')
        return value

    def create(self, validated_data):
        email = validated_data['email']
        username = validated_data['username']
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=username, email=email, password=validated_data['password']
                )
                record_account_country(user, validated_data['country'])
                return user
        except IntegrityError as err:
            message = str(err)
            if 'username' in message:
                field = 'username'
            elif 'email' in message:
                field = 'email'
            else:
                raise
            raise serializers.ValidationError(
                {field: [f'An account with this {field} already exists.']}
            )


class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['email', 'username']


class UserListSerializer(serializers.ModelSerializer):
    country = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'email', 'date_joined', 'country']

    def get_country(self, obj) -> str:
        # A plain `getattr(..., default)` on the reverse one-to-one to
        # embargo.AccountCountry: Django's related-object-missing exception is
        # deliberately an AttributeError subclass, so this returns None (not a
        # raise) for an account with no such row (e.g. created before that model
        # existed) instead of erroring.
        account_country = getattr(obj, 'accountcountry', None)
        return account_country.country if account_country else ''


class SigninSerializer(serializers.Serializer):
    email_or_username = serializers.CharField(required=True, allow_blank=False, max_length=255)
    password = serializers.CharField(required=True, allow_blank=False, write_only=True)


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True, allow_blank=False)


class PasswordResetConfirmSerializer(serializers.Serializer):
    code = serializers.CharField(required=True, allow_blank=False)
    password = serializers.CharField(
        required=True, allow_blank=False, write_only=True, validators=[validate_password_strength]
    )


class PasswordUpdateSerializer(serializers.Serializer):
    # `required=False`: whether a current password must be supplied at all depends on the
    # target account versus the caller, which this serializer has no access to - that check
    # belongs to the view (see design.md - Decisions).
    current_password = serializers.CharField(required=False, allow_blank=False, write_only=True)
    new_password = serializers.CharField(
        required=True, allow_blank=False, write_only=True, validators=[validate_password_strength]
    )


class TokenSerializer(serializers.Serializer):
    token = serializers.CharField()


class GoogleSigninSerializer(serializers.Serializer):
    access_token = serializers.CharField(required=True, allow_blank=False, write_only=True)
