from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .serializers import AccountSerializer, SignupSerializer


@extend_schema(
    summary="Health check",
    description="Reports that the service is running.",
    responses={200: {"type": "object", "properties": {"status": {"type": "string"}}}},
)
@api_view(["GET"])
def health(request):
    return Response({"status": "ok"})


@extend_schema(
    summary="Create an account",
    description=(
        "Creates one account from a username, an email address and a password. "
        "Rejections identify the offending field."
    ),
    request=SignupSerializer,
    responses={201: AccountSerializer},
)
@api_view(["POST"])
def signup(request):
    serializer = SignupSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    user = serializer.save()
    return Response(AccountSerializer(user).data, status=status.HTTP_201_CREATED)
