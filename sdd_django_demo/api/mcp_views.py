"""Endpoints that exist to serve the MCP server (mcp_server/), not the primary web/API flows.

Google sign-in, the user list, and both change-password endpoints here have no caller
but the MCP server: the web app signs in through SigninView, and only mcp_server holds
a Google OAuth client and calls these. Keeping them apart from views.py keeps that
file to the account lifecycle (signup, signin, password reset) every caller uses.
"""

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import generics, status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from embargo.rules import is_user_embargoed

from .google_auth import GoogleTokenError, resolve_google_user, verify_access_token
from .serializers import (
    AdminChangePasswordSerializer,
    GoogleAuthSerializer,
    SelfChangePasswordSerializer,
    TokenSerializer,
    UserAccountSerializer,
)
from .tenancy import organization_of, users_in

# One body for every way a Google token can be refused, so the response cannot be
# used to tell them apart.
GOOGLE_REJECTION_BODY = {'detail': 'Unable to sign in with that Google account.'}

# Separate from the body above: the token was fine, the account is the problem - no
# match, an ambiguous match, or an embargoed account. One body for all three, so it
# cannot be used to discover which addresses have accounts here.
GOOGLE_NO_ACCOUNT_BODY = {'detail': 'That Google account cannot sign in here.'}


class UserListView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = UserAccountSerializer

    def get_queryset(self):
        queryset = (
            users_in(organization_of(self.request))
            .select_related('membership', 'accountcountry')
            .order_by('pk')
        )
        country = self.request.query_params.get('country')
        if country:
            queryset = queryset.filter(accountcountry__country__iexact=country)
        username = self.request.query_params.get('username')
        if username:
            queryset = queryset.filter(membership__username__iexact=username)
        return queryset


class AdminChangePasswordView(generics.GenericAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = AdminChangePasswordSerializer

    @extend_schema(
        request=AdminChangePasswordSerializer,
        responses={
            200: OpenApiResponse(description='Password changed.'),
            400: OpenApiResponse(description='The new password was rejected.'),
            403: OpenApiResponse(description='Caller is not an admin.'),
            404: OpenApiResponse(description='No user with that username.'),
        },
    )
    def post(self, request, username, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Another organization's username is a 404, exactly like one that exists nowhere.
        user = get_object_or_404(
            users_in(organization_of(request)), membership__username=username.lower()
        )
        user.set_password(serializer.validated_data['password'])
        user.save(update_fields=['password'])
        Token.objects.filter(user=user).delete()
        return Response({'detail': 'Password changed.'}, status=status.HTTP_200_OK)


class SelfChangePasswordView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SelfChangePasswordSerializer

    @extend_schema(
        request=SelfChangePasswordSerializer,
        responses={
            200: OpenApiResponse(description='Password changed.'),
            400: OpenApiResponse(
                description='The current password was wrong, or the new password was rejected.'
            ),
            401: OpenApiResponse(description='No valid authentication credential.'),
        },
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not request.user.check_password(serializer.validated_data['current_password']):
            return Response(
                {'detail': 'Current password is incorrect.'}, status=status.HTTP_400_BAD_REQUEST
            )
        request.user.set_password(serializer.validated_data['new_password'])
        request.user.save(update_fields=['password'])
        Token.objects.filter(user=request.user).delete()
        return Response({'detail': 'Password changed.'}, status=status.HTTP_200_OK)


class GoogleAuthView(generics.GenericAPIView):
    """Sign in with a Google access token obtained elsewhere.

    A second door onto the same room as SigninView: what comes out is the same DRF
    token, so every other endpoint is unaffected. This verifies the token rather than
    exchanging a code for it, so it never holds the Google client secret.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = GoogleAuthSerializer

    @extend_schema(
        request=GoogleAuthSerializer,
        responses={
            200: OpenApiResponse(response=TokenSerializer, description='Signed in.'),
            401: OpenApiResponse(description='Google refused the token.'),
            403: OpenApiResponse(
                description='Verified with Google, but no single account here can sign in.'
            ),
        },
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            claims = verify_access_token(serializer.validated_data['access_token'])
        except GoogleTokenError:
            return Response(dict(GOOGLE_REJECTION_BODY), status=status.HTTP_401_UNAUTHORIZED)

        user = resolve_google_user(claims['email'])
        if user is None or is_user_embargoed(user):
            return Response(dict(GOOGLE_NO_ACCOUNT_BODY), status=status.HTTP_403_FORBIDDEN)

        token, _ = Token.objects.get_or_create(user=user)
        return Response({'token': token.key}, status=status.HTTP_200_OK)
