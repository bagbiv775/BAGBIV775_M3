from decimal import Decimal

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.test import RequestFactory

from core.auth import authenticated_user
from core.templatetags.shop_tags import money, stars
from orders.models import Order
from products.models import Product
from reviews.models import Review

pytestmark = pytest.mark.django_db


def test_seed_demo_is_idempotent_and_consistent(django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=False):
        call_command('seed_demo')
        call_command('seed_demo')

    assert Product.objects.count() == 12
    assert all(product.image for product in Product.objects.all())
    demo_orders = Order.objects.filter(user__username='demo')
    assert sorted(demo_orders.values_list('status', flat=True)) == ['delivered', 'pending']
    for review in Review.objects.all():
        assert Order.objects.filter(
            user=review.user, status='delivered', items__product=review.product
        ).exists()


def test_seed_demo_catalog_only():
    call_command('seed_demo', '--no-users')
    assert Product.objects.count() == 12
    assert not Order.objects.exists()


@pytest.mark.parametrize(
    ('value', 'expected'),
    [(Decimal('1234.5'), '$1,234.50'), ('5', '$5.00'), (None, ''), ('abc', '')],
)
def test_money_filter(value, expected):
    assert money(value) == expected


def test_stars_filter():
    assert stars(4.4) == [True, True, True, True, False]
    assert stars(None) == [False] * 5


def test_authenticated_user_helper(user):
    request = RequestFactory().get('/')
    request.user = AnonymousUser()
    with pytest.raises(PermissionDenied):
        authenticated_user(request)
    request.user = user
    assert authenticated_user(request) == user
