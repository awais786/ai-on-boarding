from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import generics
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .serializers import AccountSerializer, SignupSerializer


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
