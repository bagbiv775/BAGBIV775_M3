from django.db.models import QuerySet
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.request import Request
from rest_framework.response import Response

from products.api.filters import ProductFilter
from products.api.serializers import ProductSerializer
from products.models import Product
from reviews.api.serializers import ReviewSerializer
from reviews.models import Review


@extend_schema_view(
    list=extend_schema(
        summary='Список товаров',
        description=(
            'Только активные товары. Пагинация `?page=`, поиск `?search=` по названию и '
            'описанию, сортировка `?ordering=` по `price`, `created_at`, `popularity`, `name` '
            '(минус — по убыванию).'
        ),
    ),
    retrieve=extend_schema(summary='Товар', description='Детальная информация и средний рейтинг.'),
)
class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProductSerializer
    filterset_class = ProductFilter
    search_fields = ('name', 'description')
    ordering_fields = ('price', 'created_at', 'popularity', 'name')
    ordering = ('-created_at', '-pk')
    permission_classes = (IsAuthenticatedOrReadOnly,)

    def get_queryset(self) -> QuerySet[Product]:
        return Product.objects.active().select_related('category').with_rating().with_popularity()

    @extend_schema(
        methods=['GET'],
        summary='Отзывы о товаре',
        responses=ReviewSerializer(many=True),
        filters=False,
    )
    @extend_schema(
        methods=['POST'],
        summary='Оставить отзыв',
        description='Только для покупателей, получивших товар (заказ в статусе `delivered`). '
        'Один отзыв на товар, оценка 1–5.',
        request=ReviewSerializer,
        responses={201: ReviewSerializer, 400: OpenApiResponse(description='Отзыв не принят')},
    )
    @action(detail=True, methods=['get', 'post'], filter_backends=[], pagination_class=None)
    def reviews(self, request: Request, pk: str | None = None) -> Response:
        product = self.get_object()
        if request.method == 'POST':
            serializer = ReviewSerializer(
                data=request.data, context={'request': request, 'product': product}
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        reviews = Review.objects.filter(product=product).select_related('user')
        return Response(ReviewSerializer(reviews, many=True).data)
