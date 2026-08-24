from datetime import timedelta

from django.contrib.auth import authenticate
from django.db.models import Case, F, Q, Value, When
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import generics
from rest_framework.decorators import api_view
from rest_framework.authtoken.models import Token
from rest_framework.response import Response

from embargo.models import AccountCountry
from embargo.rules import is_blocked

from .models import SigninAttempt
from .serializers import AccountSerializer, SigninSerializer, SignupSerializer, TokenSerializer

LOCKOUT_THRESHOLD = 3
LOCKOUT_WINDOW = timedelta(minutes=5)
LOCKOUT_DURATION = timedelta(minutes=30)
SIGNIN_REJECTION_BODY = {'detail': 'Unable to sign in with the provided credentials.'}


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
            200: OpenApiResponse(response=TokenSerializer, description='Signed in.'),
            401: OpenApiResponse(
                description='Rejected: unregistered email, wrong password, locked out, or the '
                'account is embargoed - identical in status and body for all four.'
            ),
        },
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email'].lower()
        password = serializer.validated_data['password']

        attempt, _ = SigninAttempt.objects.get_or_create(email=email)
        now = timezone.now()

        if (
            attempt.failed_count >= LOCKOUT_THRESHOLD
            and attempt.last_failed_at is not None
            and now < attempt.last_failed_at + LOCKOUT_DURATION
        ):
            return Response(SIGNIN_REJECTION_BODY, status=401)

        user = authenticate(username=email, password=password)

        if user is not None:
            account_country = AccountCountry.objects.filter(user=user).first()
            if account_country is not None and is_blocked(account_country.country):
                return Response(SIGNIN_REJECTION_BODY, status=401)

            SigninAttempt.objects.filter(email=email).update(failed_count=0)
            token, _ = Token.objects.get_or_create(user=user)
            return Response({'token': token.key}, status=200)

        # A single atomic UPDATE, not a Python read-modify-write: the reset-vs-increment
        # decision and the write happen in one server-side statement, so concurrent failed
        # attempts against the same email can't race and lose an update (unlike
        # select_for_update(), which is a silent no-op on this project's SQLite backend).
        SigninAttempt.objects.filter(email=email).update(
            failed_count=Case(
                When(
                    Q(last_failed_at__isnull=True) | Q(last_failed_at__lt=now - LOCKOUT_WINDOW),
                    then=Value(1),
                ),
                default=F('failed_count') + 1,
            ),
            last_failed_at=now,
        )

        return Response(SIGNIN_REJECTION_BODY, status=401)
