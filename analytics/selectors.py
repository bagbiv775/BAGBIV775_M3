"""Read-only sales analytics shared by the admin dashboard and GraphQL.

Revenue-type metrics only count orders in SOLD_STATUSES (paid, shipped,
delivered); pending and cancelled orders bring no money.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.db.models import Avg, Count, Q, QuerySet, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from orders.models import SOLD_STATUSES, Order
from products.models import Product, ProductQuerySet


@dataclass(frozen=True)
class SalesSummary:
    revenue: Decimal
    sold_orders: int
    average_order_value: Decimal
    total_orders: int


@dataclass(frozen=True)
class DailyRevenue:
    day: date
    revenue: Decimal
    orders: int


def sold_orders() -> QuerySet[Order]:
    return Order.objects.filter(status__in=SOLD_STATUSES)


def sales_summary() -> SalesSummary:
    totals = sold_orders().aggregate(
        revenue=Sum('total_price'),
        count=Count('pk'),
        average=Avg('total_price'),
    )
    return SalesSummary(
        revenue=totals['revenue'] or Decimal('0'),
        sold_orders=totals['count'],
        average_order_value=(totals['average'] or Decimal('0')).quantize(Decimal('0.01')),
        total_orders=Order.objects.count(),
    )


def orders_by_status() -> list[tuple[str, str, int]]:
    """(status value, human label, order count) for every status, zero included."""
    counts = dict(Order.objects.values_list('status').annotate(total=Count('pk')))
    return [(value, label, counts.get(value, 0)) for value, label in Order.Status.choices]


def top_products(limit: int = 5) -> ProductQuerySet:
    return (
        Product.objects.with_popularity()
        .filter(popularity__gt=0)  # type: ignore[misc]  # annotation from with_popularity()
        .select_related('category')
        .order_by('-popularity', 'name')[:limit]
    )


def low_stock_products(threshold: int = 10, limit: int = 10) -> ProductQuerySet:
    return (
        Product.objects.active()
        .filter(stock__lte=threshold)
        .select_related('category')
        .order_by('stock', 'name')[:limit]
    )


def daily_revenue(days: int = 30) -> list[DailyRevenue]:
    since = timezone.localdate() - timedelta(days=days - 1)
    rows = (
        sold_orders()
        .filter(created_at__date__gte=since)
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(revenue=Sum('total_price'), orders=Count('pk'))
        .order_by('day')
    )
    return [DailyRevenue(row['day'], row['revenue'], row['orders']) for row in rows]


def customer_activity() -> dict[str, int]:
    """How many customers ordered at all, and how many came back for a second purchase."""
    customers = User.objects.annotate(
        sold_count=Count('orders', filter=Q(orders__status__in=SOLD_STATUSES)),
        order_count=Count('orders'),
    )
    return {
        'registered': User.objects.count(),
        'with_orders': customers.filter(order_count__gt=0).count(),
        'buyers': customers.filter(sold_count__gt=0).count(),
        'repeat_buyers': customers.filter(sold_count__gt=1).count(),
    }


@dataclass(frozen=True)
class CustomerStats:
    username: str
    orders_count: int
    total_spent: Decimal


def repeat_customers(limit: int = 10) -> list[CustomerStats]:
    """Customers with more than one sold order, best spenders first."""
    rows = (
        User.objects.annotate(
            orders_count=Count('orders', filter=Q(orders__status__in=SOLD_STATUSES)),
            total_spent=Sum('orders__total_price', filter=Q(orders__status__in=SOLD_STATUSES)),
        )
        .filter(orders_count__gt=1)
        .order_by('-total_spent', 'username')
        .values('username', 'orders_count', 'total_spent')[:limit]
    )
    return [CustomerStats(**row) for row in rows]
