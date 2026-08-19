from django.contrib.auth import get_user_model
from rest_framework import serializers

User = get_user_model()

PASSWORD_MIN_LENGTH = 8


class SignupSerializer(serializers.Serializer):
    """Validates a signup submission and creates the account.

    Satisfies FR-001 through FR-010 and FR-014.
    """

    username = serializers.CharField(allow_blank=False)
    email = serializers.EmailField(allow_blank=False)
    password = serializers.CharField(
        allow_blank=False,
        min_length=PASSWORD_MIN_LENGTH,
        write_only=True,
    )

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("That username is already registered.")
        return value

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("That email address is already registered.")
        return value

    def create(self, validated_data):
        return User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"],
        )


class AccountSerializer(serializers.Serializer):
    """The signup response. Carries no password field of any kind (FR-011)."""

    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)
