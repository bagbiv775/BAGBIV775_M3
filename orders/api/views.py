from django.db.models import QuerySet
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from core.auth import authenticated_user
from orders.api.serializers import OrderCreateSerializer, OrderSerializer
from orders.models import Order
from orders.services import OrderError, cancel_order_by_customer


@extend_schema_view(
    list=extend_schema(summary='Мои заказы'),
    retrieve=extend_schema(summary='Мой заказ', description='Чужой заказ — 404.'),
    create=extend_schema(
        summary='Создать заказ',
        description='Позиции, адрес доставки и способ оплаты. Цены берутся из базы, '
        'итог и статус `pending` рассчитывает сервер. Остатки резервируются сразу; '
        'при любой ошибке заказ не создаётся.',
        request=OrderCreateSerializer,
        responses={201: OrderSerializer, 400: OpenApiResponse(description='Ошибка валидации')},
    ),
)
class OrderViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Orders of the authenticated user. PUT, PATCH and DELETE are not available."""

    permission_classes = (IsAuthenticated,)
    filter_backends = ()

    def get_queryset(self) -> QuerySet[Order]:
        if getattr(self, 'swagger_fake_view', False):  # schema generation, no real user
            return Order.objects.none()
        return (
            Order.objects.filter(user=authenticated_user(self.request))
            .prefetch_related('items__product')
            .order_by('-created_at', '-pk')
        )

    def get_serializer_class(self) -> type[BaseSerializer]:
        return OrderCreateSerializer if self.action == 'create' else OrderSerializer

    @extend_schema(
        summary='Отменить заказ',
        description='Доступно только для своего заказа в статусе `pending`. '
        'Товары возвращаются на склад.',
        request=None,
        responses={200: OrderSerializer, 400: OpenApiResponse(description='Отмена недоступна')},
    )
    @action(detail=True, methods=['post'])
    def cancel(self, request: Request, pk: str | None = None) -> Response:
        order = self.get_object()
        try:
            cancel_order_by_customer(order, authenticated_user(request))
        except OrderError as error:
            return Response(
                {'detail': ' '.join(error.messages)}, status=status.HTTP_400_BAD_REQUEST
            )
        order.refresh_from_db()
        return Response(OrderSerializer(order, context=self.get_serializer_context()).data)
