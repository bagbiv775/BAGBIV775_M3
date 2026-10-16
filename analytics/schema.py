"""GraphQL schema with read-only sales analytics for shop staff."""

from typing import Any

import graphene
from graphql import GraphQLError, GraphQLResolveInfo

from analytics import selectors


def require_staff(info: GraphQLResolveInfo) -> None:
    user = info.context.user
    if not (user.is_authenticated and user.is_staff):
        raise GraphQLError('Аналитика доступна только сотрудникам магазина (is_staff).')


class SalesSummaryType(graphene.ObjectType):
    revenue = graphene.Decimal(required=True, description='Выручка по оплаченным заказам')
    sold_orders = graphene.Int(required=True, description='Оплаченные/отправленные/доставленные')
    average_order_value = graphene.Decimal(required=True, description='Средний чек')
    total_orders = graphene.Int(
        required=True, description='Все заказы, включая pending и cancelled'
    )


class StatusCountType(graphene.ObjectType):
    status = graphene.String(required=True)
    label = graphene.String(required=True)
    count = graphene.Int(required=True)


class DailyRevenueType(graphene.ObjectType):
    day = graphene.Date(required=True)
    revenue = graphene.Decimal(required=True)
    orders = graphene.Int(required=True)


class ProductStatsType(graphene.ObjectType):
    id = graphene.ID(required=True)
    name = graphene.String(required=True)
    slug = graphene.String(required=True)
    category = graphene.String(required=True)
    stock = graphene.Int(required=True)
    sold = graphene.Int(required=True, description='Продано единиц')


class CustomerActivityType(graphene.ObjectType):
    registered = graphene.Int(required=True)
    with_orders = graphene.Int(required=True, description='Оформили хотя бы один заказ')
    buyers = graphene.Int(required=True, description='Есть хотя бы один оплаченный заказ')
    repeat_buyers = graphene.Int(required=True, description='Больше одного оплаченного заказа')


class CustomerStatsType(graphene.ObjectType):
    username = graphene.String(required=True)
    orders_count = graphene.Int(required=True)
    total_spent = graphene.Decimal(required=True)


def _product_stats(products: Any) -> list[ProductStatsType]:
    return [
        ProductStatsType(
            id=product.pk,
            name=product.name,
            slug=product.slug,
            category=product.category.name,
            stock=product.stock,
            sold=getattr(product, 'popularity', 0),
        )
        for product in products
    ]


class Query(graphene.ObjectType):
    sales_summary = graphene.Field(SalesSummaryType, required=True)
    orders_by_status = graphene.List(graphene.NonNull(StatusCountType), required=True)
    revenue_trend = graphene.List(
        graphene.NonNull(DailyRevenueType),
        required=True,
        days=graphene.Int(default_value=30, description='Период в днях'),
    )
    top_products = graphene.List(
        graphene.NonNull(ProductStatsType), required=True, limit=graphene.Int(default_value=5)
    )
    low_stock_products = graphene.List(
        graphene.NonNull(ProductStatsType),
        required=True,
        threshold=graphene.Int(default_value=10),
        limit=graphene.Int(default_value=10),
    )
    customer_activity = graphene.Field(CustomerActivityType, required=True)
    repeat_customers = graphene.List(
        graphene.NonNull(CustomerStatsType), required=True, limit=graphene.Int(default_value=10)
    )

    def resolve_sales_summary(self, info: GraphQLResolveInfo) -> selectors.SalesSummary:
        require_staff(info)
        return selectors.sales_summary()

    def resolve_orders_by_status(self, info: GraphQLResolveInfo) -> list[StatusCountType]:
        require_staff(info)
        return [
            StatusCountType(status=value, label=label, count=count)
            for value, label, count in selectors.orders_by_status()
        ]

    def resolve_revenue_trend(self, info: GraphQLResolveInfo, days: int) -> list[Any]:
        require_staff(info)
        if not 1 <= days <= 366:
            raise GraphQLError('Параметр days должен быть от 1 до 366.')
        return selectors.daily_revenue(days=days)

    def resolve_top_products(self, info: GraphQLResolveInfo, limit: int) -> list[ProductStatsType]:
        require_staff(info)
        return _product_stats(selectors.top_products(limit=min(max(limit, 1), 100)))

    def resolve_low_stock_products(
        self, info: GraphQLResolveInfo, threshold: int, limit: int
    ) -> list[ProductStatsType]:
        require_staff(info)
        return _product_stats(
            selectors.low_stock_products(threshold=threshold, limit=min(max(limit, 1), 100))
        )

    def resolve_customer_activity(self, info: GraphQLResolveInfo) -> CustomerActivityType:
        require_staff(info)
        return CustomerActivityType(**selectors.customer_activity())

    def resolve_repeat_customers(self, info: GraphQLResolveInfo, limit: int) -> list[Any]:
        require_staff(info)
        return selectors.repeat_customers(limit=min(max(limit, 1), 100))


schema = graphene.Schema(query=Query)
