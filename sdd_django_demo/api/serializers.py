import re

from django.contrib.auth.models import User
from django.core.validators import validate_email
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

PASSWORD_MIN_LENGTH = 8


def validate_password_strength(value):
    if len(value) < PASSWORD_MIN_LENGTH:
        raise serializers.ValidationError(
            f'Must be at least {PASSWORD_MIN_LENGTH} characters and contain a letter and a digit.'
        )
    if not re.search(r'[A-Za-z]', value) or not re.search(r'\d', value):
        raise serializers.ValidationError(
            f'Must be at least {PASSWORD_MIN_LENGTH} characters and contain a letter and a digit.'
        )


class SignupSerializer(serializers.Serializer):
    email = serializers.CharField(required=True, allow_blank=False)
    password = serializers.CharField(
        required=True, allow_blank=False, write_only=True, validators=[validate_password_strength]
    )

    def validate_email(self, value):
        try:
            validate_email(value)
        except DjangoValidationError:
            raise serializers.ValidationError('Enter a valid email address.')

        normalised = value.lower()
        if User.objects.filter(email=normalised).exists():
            raise serializers.ValidationError('An account with this email already exists.')
        return normalised

    def create(self, validated_data):
        email = validated_data['email']
        return User.objects.create_user(
            username=email, email=email, password=validated_data['password']
        )


class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['email']
