from datetime import timedelta

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import generics
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import SigninAttempt
from .serializers import AccountSerializer, SigninSerializer, SignupSerializer

MAX_FAILURES = 3
FAILURE_WINDOW = timedelta(minutes=5)
LOCKOUT_DURATION = timedelta(minutes=30)

REJECTED_RESPONSE = {'detail': 'Unable to sign in with the provided credentials.'}


@api_view(['GET'])
def health(request):
    return Response({'status': 'ok'})


class SignupView(generics.CreateAPIView):
    serializer_class = SignupSerializer

    @extend_schema(
        request=SignupSerializer,
        responses={
            200: OpenApiResponse(response=AccountSerializer, description='Account created.'),
            400: OpenApiResponse(description='Validation failed; body names the offending field.'),
        },
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(AccountSerializer(user).data, status=200)


class SigninView(generics.GenericAPIView):
    serializer_class = SigninSerializer

    @extend_schema(
        request=SigninSerializer,
        responses={
            200: OpenApiResponse(description='Signin succeeded; body contains an auth token.'),
            401: OpenApiResponse(
                description='Signin rejected - missing field, unregistered email or username, '
                'wrong password, or lockout.'
            ),
        },
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=401)

        email_or_username = serializer.validated_data['email_or_username'].lower()
        password = serializer.validated_data['password']

        candidate = User.objects.filter(
            Q(email=email_or_username) | Q(username=email_or_username)
        ).first()
        attempt_key = candidate.email if candidate is not None else email_or_username

        with transaction.atomic():
            SigninAttempt.objects.get_or_create(email_or_username=attempt_key)
            attempt = SigninAttempt.objects.select_for_update().get(
                email_or_username=attempt_key
            )
            now = timezone.now()

            if (
                attempt.failed_count >= MAX_FAILURES
                and attempt.last_failed_at is not None
                and now - attempt.last_failed_at < LOCKOUT_DURATION
            ):
                return Response(REJECTED_RESPONSE, status=401)

            user = None
            if candidate is not None:
                user = authenticate(username=candidate.username, password=password)

            if user is None:
                if (
                    attempt.last_failed_at is None
                    or now - attempt.last_failed_at >= FAILURE_WINDOW
                ):
                    attempt.failed_count = 1
                else:
                    attempt.failed_count += 1
                attempt.last_failed_at = now
                attempt.save()
                return Response(REJECTED_RESPONSE, status=401)

            attempt.failed_count = 0
            attempt.save()

        token, _ = Token.objects.get_or_create(user=user)
        return Response({'token': token.key}, status=200)
