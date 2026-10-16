from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.permissions import AllowAny

from users.api.serializers import RegisterSerializer


@extend_schema(
    summary='Регистрация',
    description='Создаёт пользователя и сразу возвращает пару JWT-токенов.',
)
class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = (AllowAny,)
    authentication_classes = ()
