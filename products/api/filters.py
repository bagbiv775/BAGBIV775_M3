import django_filters
from django.db.models import QuerySet

from products.models import Product


class ProductFilter(django_filters.FilterSet):
    category = django_filters.CharFilter(
        field_name='category__slug', help_text='Slug категории, например `hops`.'
    )
    min_price = django_filters.NumberFilter(field_name='price', lookup_expr='gte')
    max_price = django_filters.NumberFilter(field_name='price', lookup_expr='lte')
    in_stock = django_filters.BooleanFilter(
        method='filter_in_stock', help_text='Только товары в наличии.'
    )

    class Meta:
        model = Product
        fields = ['category', 'min_price', 'max_price', 'in_stock']

    def filter_in_stock(
        self, queryset: QuerySet[Product], name: str, value: bool
    ) -> QuerySet[Product]:
        return queryset.filter(stock__gt=0) if value else queryset.filter(stock=0)
