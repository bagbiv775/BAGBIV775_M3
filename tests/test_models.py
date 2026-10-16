from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from orders.models import Order, OrderItem
from products.models import Product
from reviews.models import Review

pytestmark = pytest.mark.django_db


def test_string_representations(product, user, make_order):
    order = make_order(user, [(product, 1)])
    review = Review(product=product, user=user, rating=5, comment='ok')
    assert str(product) == 'Хмель Citra'
    assert str(product.category) == 'Хмель'
    assert str(order) == f'Заказ №{order.pk}'
    assert str(order.items.get()) == 'Хмель Citra × 1'
    assert 'Хмель Citra' in str(review)
    assert product.get_absolute_url() == '/product/citra/'
    assert order.get_absolute_url() == f'/account/orders/{order.pk}/'


@pytest.mark.parametrize(
    ('field', 'value'),
    [('price', Decimal('-1')), ('stock', -1)],
)
def test_product_check_constraints(make_product, field, value):
    with pytest.raises(IntegrityError), transaction.atomic():
        make_product(**{field: value})


def test_order_total_cannot_be_negative(user):
    with pytest.raises(IntegrityError), transaction.atomic():
        Order.objects.create(
            user=user, payment_method='card', shipping_address='x', total_price=Decimal('-1')
        )


@pytest.mark.parametrize(('quantity', 'price'), [(0, Decimal('1')), (1, Decimal('-1'))])
def test_order_item_check_constraints(user, product, quantity, price):
    order = Order.objects.create(user=user, payment_method='card', shipping_address='x')
    with pytest.raises(IntegrityError), transaction.atomic():
        OrderItem.objects.create(order=order, product=product, quantity=quantity, price=price)


def test_order_item_unique_per_product(user, product):
    order = Order.objects.create(user=user, payment_method='card', shipping_address='x')
    OrderItem.objects.create(order=order, product=product, quantity=1, price=Decimal('1'))
    with pytest.raises(IntegrityError), transaction.atomic():
        OrderItem.objects.create(order=order, product=product, quantity=2, price=Decimal('1'))


@pytest.mark.parametrize('rating', [0, 6])
def test_review_rating_constraint(user, product, rating):
    with pytest.raises(IntegrityError), transaction.atomic():
        Review.objects.create(user=user, product=product, rating=rating, comment='x')


def test_review_unique_per_user_and_product(user, product):
    Review.objects.create(user=user, product=product, rating=5, comment='x')
    with pytest.raises(IntegrityError), transaction.atomic():
        Review.objects.create(user=user, product=product, rating=4, comment='y')


def test_ordered_product_and_customer_are_protected(user, product, make_order):
    make_order(user, [(product, 1)])
    with pytest.raises(ProtectedError):
        product.delete()
    with pytest.raises(ProtectedError):
        user.delete()


def test_category_with_products_is_protected(product):
    with pytest.raises(ProtectedError):
        product.category.delete()


def test_rating_annotation_is_average_or_none(product, make_product, make_user):
    unrated = make_product()
    for rating in (5, 4, 3):
        Review.objects.create(user=make_user(), product=product, rating=rating, comment='x')

    ratings = dict(Product.objects.with_rating().values_list('pk', 'avg_rating'))
    assert ratings[product.pk] == pytest.approx(4.0)
    assert ratings[unrated.pk] is None


def test_popularity_counts_only_sold_statuses(product, make_user, make_order):
    buyer = make_user()
    make_order(buyer, [(product, 2)], status=Order.Status.PAID)
    make_order(buyer, [(product, 1)], status=Order.Status.SHIPPED)
    make_order(buyer, [(product, 3)], status=Order.Status.DELIVERED)
    make_order(buyer, [(product, 1)], status=Order.Status.PENDING)
    make_order(buyer, [(product, 1)], status=Order.Status.CANCELLED)

    assert Product.objects.with_popularity().get(pk=product.pk).popularity == 6


def test_rating_and_popularity_combined_do_not_multiply(product, make_user, make_order):
    for rating in (5, 3):
        buyer = make_user()
        make_order(buyer, [(product, 2)], status=Order.Status.DELIVERED)
        Review.objects.create(user=buyer, product=product, rating=rating, comment='x')

    annotated = Product.objects.with_rating().with_popularity().get(pk=product.pk)
    assert annotated.popularity == 4
    assert annotated.avg_rating == pytest.approx(4.0)


def test_order_helpers(user, product, make_order):
    order = make_order(user, [(product, 2)])
    assert order.can_be_cancelled_by_customer
    assert order.can_change_status_to(Order.Status.PAID)
    assert not order.can_change_status_to(Order.Status.DELIVERED)
    assert order.items.get().line_total == Decimal('11.98')
    assert product.is_available
