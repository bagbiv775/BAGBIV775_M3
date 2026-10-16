from decimal import Decimal

import pytest
from django.contrib.messages import get_messages
from django.contrib.sessions.backends.db import SessionStore
from django.urls import reverse

from orders.cart import Cart, CartError

pytestmark = pytest.mark.django_db

CART = reverse('orders:cart')


def add_url(product):
    return reverse('orders:cart_add', args=[product.pk])


def update_url(product):
    return reverse('orders:cart_update', args=[product.pk])


def cart_quantities(client):
    return client.session.get('cart', {})


def last_message(response):
    return [str(m) for m in get_messages(response.wsgi_request)][-1]


def test_empty_cart(client):
    response = client.get(CART)
    assert response.status_code == 200
    assert 'Корзина пуста' in response.text


def test_add_to_cart_accumulates(client, product):
    client.post(add_url(product), {'quantity': 2})
    response = client.post(add_url(product), {'quantity': 3})
    assert cart_quantities(client) == {str(product.pk): 5}
    assert 'в корзине: 5 шт.' in last_message(response)
    assert response.url == product.get_absolute_url()


def test_add_redirects_to_safe_next_only(client, product):
    assert client.post(add_url(product), {'quantity': 1, 'next': '/cart/'}).url == '/cart/'
    evil = client.post(add_url(product), {'quantity': 1, 'next': 'https://evil.example/'})
    assert evil.url == product.get_absolute_url()


def test_cannot_add_more_than_stock(client, product):
    client.post(add_url(product), {'quantity': 8})
    response = client.post(add_url(product), {'quantity': 3})
    assert cart_quantities(client) == {str(product.pk): 8}
    assert 'в наличии 10 шт.' in last_message(response)


@pytest.mark.parametrize('quantity', ['0', '-1', 'abc'])
def test_invalid_add_quantity(client, product, quantity):
    response = client.post(add_url(product), {'quantity': quantity})
    assert cart_quantities(client) == {}
    assert 'не меньше 1' in last_message(response)


def test_inactive_product_cannot_be_added(client, make_product):
    hidden = make_product(is_active=False)
    assert client.post(add_url(hidden), {'quantity': 1}).status_code == 404


def test_add_requires_post(client, product):
    assert client.get(add_url(product)).status_code == 405


def test_update_and_remove(client, product, make_product):
    other = make_product(price=Decimal('1.50'))
    client.post(add_url(product), {'quantity': 1})
    client.post(add_url(other), {'quantity': 1})

    client.post(update_url(product), {'quantity': 4})
    assert cart_quantities(client)[str(product.pk)] == 4

    response = client.post(update_url(product), {'quantity': 11})
    assert cart_quantities(client)[str(product.pk)] == 4
    assert 'в наличии 10' in last_message(response)

    client.post(update_url(other), {'quantity': 0})
    assert str(other.pk) not in cart_quantities(client)

    client.post(reverse('orders:cart_remove', args=[product.pk]))
    assert cart_quantities(client) == {}


def test_update_with_garbage_quantity(client, product):
    client.post(add_url(product), {'quantity': 1})
    response = client.post(update_url(product), {'quantity': 'x'})
    assert last_message(response) == 'Некорректное количество.'


def test_cart_page_totals_and_header_badge(client, product, make_product):
    other = make_product(price=Decimal('2.50'))
    client.post(add_url(product), {'quantity': 2})
    client.post(add_url(other), {'quantity': 3})
    response = client.get(CART)
    assert response.context['total'] == Decimal('19.48')
    assert '$19.48' in response.text
    assert response.context['cart_count'] == 5
    assert 'Оформить заказ' in response.text


def test_cart_flags_items_that_became_unavailable(client, product):
    client.post(add_url(product), {'quantity': 5})
    product.stock = 2
    product.save()
    response = client.get(CART)
    assert response.context['has_problems']
    assert 'В наличии только 2 шт.' in response.text
    assert 'Оформить заказ' not in response.text


def test_cart_survives_login(client, user, product):
    client.post(add_url(product), {'quantity': 3})
    client.post(reverse('users:login'), {'username': user.username, 'password': 'Pass12345!'})
    assert '_auth_user_id' in client.session
    assert cart_quantities(client) == {str(product.pk): 3}


class TestCartObject:
    def make_cart(self):
        session = SessionStore()
        session.create()
        return Cart(session)

    def test_set_remove_clear_and_lines(self, product, make_product):
        cart = self.make_cart()
        other = make_product()
        cart.add(product, 2)
        cart.set(other, 1)
        assert len(cart) == 3
        assert {line.product_id for line in cart.as_order_lines()} == {product.pk, other.pk}
        assert Cart.total_of(cart.items()) == Decimal('21.98')
        assert cart.set(other, 0) == 0
        cart.remove(999)
        cart.clear()
        assert not cart
        assert cart.items() == []

    def test_errors(self, product, make_product):
        cart = self.make_cart()
        with pytest.raises(CartError):
            cart.add(product, 0)
        with pytest.raises(CartError):
            cart.set(make_product(is_active=False), 1)

    def test_problem_messages(self, product):
        cart = self.make_cart()
        cart.add(product, 1)
        product.is_active = False
        product.save()
        assert cart.items()[0].problem == 'Товар снят с продажи.'
        product.is_active, product.stock = True, 0
        product.save()
        assert cart.items()[0].problem == 'Товара нет в наличии.'
        product.stock = 5
        product.save()
        assert cart.items()[0].problem is None

    def test_deleted_products_disappear(self, make_product):
        cart = self.make_cart()
        doomed = make_product()
        cart.add(doomed, 1)
        doomed.delete()
        assert cart.items() == []
        assert len(cart) == 0
