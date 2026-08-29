import re

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from rest_framework import serializers

from embargo.rules import is_blocked, record_account_country

PASSWORD_MIN_LENGTH = 8


def validate_password_strength(value):
    if (
        len(value) < PASSWORD_MIN_LENGTH
        or not re.search(r'[A-Za-z]', value)
        or not re.search(r'\d', value)
    ):
        raise serializers.ValidationError(
            f'Must be at least {PASSWORD_MIN_LENGTH} characters and contain a letter and a digit.'
        )


class SignupSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True, allow_blank=False)
    password = serializers.CharField(
        required=True, allow_blank=False, write_only=True, validators=[validate_password_strength]
    )
    country = serializers.CharField(required=True, allow_blank=False, max_length=100)

    def validate_email(self, value):
        normalised = value.lower()
        if User.objects.filter(email=normalised).exists():
            raise serializers.ValidationError('An account with this email already exists.')
        return normalised

    def validate_country(self, value):
        if is_blocked(value):
            raise serializers.ValidationError('Signups from this country are not allowed.')
        return value

    def create(self, validated_data):
        email = validated_data['email']
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=email, email=email, password=validated_data['password']
                )
                record_account_country(user, validated_data['country'])
                return user
        except IntegrityError:
            raise serializers.ValidationError(
                {'email': ['An account with this email already exists.']}
            )


class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['email']


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True, allow_blank=False)


class PasswordResetConfirmSerializer(serializers.Serializer):
    code = serializers.CharField(required=True, allow_blank=False)
    password = serializers.CharField(
        required=True, allow_blank=False, write_only=True, validators=[validate_password_strength]
    )


class SigninSerializer(serializers.Serializer):
    email = serializers.CharField(required=True, allow_blank=False, max_length=254)
    password = serializers.CharField(required=True, allow_blank=False, write_only=True)


class TokenSerializer(serializers.Serializer):
    token = serializers.CharField()
