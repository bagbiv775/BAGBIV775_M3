from collections.abc import Callable
from decimal import Decimal
from itertools import count
from typing import Any

import pytest
from django.contrib.auth.models import User
from django.test import Client
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from orders.models import Order
from orders.services import OrderLine, change_order_status, create_order
from products.models import Category, Product

_sequence = count(1)


@pytest.fixture(autouse=True)
def _fast_and_isolated(settings: Any, tmp_path: Any) -> None:
    settings.PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
    settings.MEDIA_ROOT = tmp_path / 'media'
    settings.STORAGES = {
        **settings.STORAGES,
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    }


@pytest.fixture
def category(db: Any) -> Category:
    return Category.objects.create(name='Хмель', slug='hops')


@pytest.fixture
def make_category(db: Any) -> Callable[..., Category]:
    def factory(**kwargs: Any) -> Category:
        number = next(_sequence)
        kwargs.setdefault('name', f'Категория {number}')
        kwargs.setdefault('slug', f'category-{number}')
        return Category.objects.create(**kwargs)

    return factory


@pytest.fixture
def make_product(category: Category) -> Callable[..., Product]:
    def factory(**kwargs: Any) -> Product:
        number = next(_sequence)
        kwargs.setdefault('name', f'Товар {number}')
        kwargs.setdefault('slug', f'product-{number}')
        kwargs.setdefault('description', 'Описание товара')
        kwargs.setdefault('price', Decimal('10.00'))
        kwargs.setdefault('stock', 10)
        kwargs.setdefault('category', category)
        return Product.objects.create(**kwargs)

    return factory


@pytest.fixture
def product(make_product: Callable[..., Product]) -> Product:
    return make_product(name='Хмель Citra', slug='citra', price=Decimal('5.99'), stock=10)


@pytest.fixture
def make_user(db: Any) -> Callable[..., User]:
    def factory(username: str | None = None, **kwargs: Any) -> User:
        username = username or f'user{next(_sequence)}'
        kwargs.setdefault('email', f'{username}@example.com')
        return User.objects.create_user(username=username, password='Pass12345!', **kwargs)

    return factory


@pytest.fixture
def user(make_user: Callable[..., User]) -> User:
    return make_user('buyer')


@pytest.fixture
def other_user(make_user: Callable[..., User]) -> User:
    return make_user('stranger')


@pytest.fixture
def staff_user(make_user: Callable[..., User]) -> User:
    return make_user('manager', is_staff=True, is_superuser=True)


@pytest.fixture
def auth_client(client: Client, user: User) -> Client:
    client.force_login(user)
    return client


@pytest.fixture
def admin_web_client(client: Client, staff_user: User) -> Client:
    client.force_login(staff_user)
    return client


def jwt_client_for(user: User) -> APIClient:
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}')
    return api


@pytest.fixture
def make_jwt_client(db: Any) -> Callable[[User], APIClient]:
    return jwt_client_for


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def jwt_client(user: User) -> APIClient:
    return jwt_client_for(user)


@pytest.fixture
def make_order(db: Any) -> Callable[..., Order]:
    """Create an order through the service and move it along to `status`."""

    path = {
        Order.Status.PENDING: [],
        Order.Status.PAID: [Order.Status.PAID],
        Order.Status.SHIPPED: [Order.Status.PAID, Order.Status.SHIPPED],
        Order.Status.DELIVERED: [Order.Status.PAID, Order.Status.SHIPPED, Order.Status.DELIVERED],
        Order.Status.CANCELLED: [Order.Status.CANCELLED],
    }

    def factory(
        user: User,
        items: list[tuple[Product, int]],
        status: str = Order.Status.PENDING,
        **kwargs: Any,
    ) -> Order:
        kwargs.setdefault('shipping_address', 'Алматы, ул. Абая, 1')
        kwargs.setdefault('payment_method', Order.PaymentMethod.CARD)
        order = create_order(
            user=user,
            lines=[OrderLine(product.pk, quantity) for product, quantity in items],
            **kwargs,
        )
        for next_status in path[status]:
            change_order_status(order, next_status)
        return order

    return factory
