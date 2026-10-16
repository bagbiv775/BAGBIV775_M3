from decimal import Decimal

import pytest

from orders.models import Order, OrderItem
from orders.services import (
    OrderError,
    OrderLine,
    cancel_order_by_customer,
    change_order_status,
    create_order,
    merge_lines,
)

pytestmark = pytest.mark.django_db

S = Order.Status


def _create(user, lines, **kwargs):
    kwargs.setdefault('shipping_address', 'Алматы')
    kwargs.setdefault('payment_method', Order.PaymentMethod.CARD)
    return create_order(user=user, lines=lines, **kwargs)


def test_create_order_reserves_stock_and_snapshots_prices(user, make_product):
    hops = make_product(price=Decimal('5.99'), stock=10)
    malt = make_product(price=Decimal('2.50'), stock=3)

    order = _create(user, [OrderLine(hops.pk, 2), OrderLine(malt.pk, 3)])

    assert order.status == S.PENDING
    assert order.user == user
    assert order.total_price == Decimal('19.48')
    assert {(i.product_id, i.quantity, i.price) for i in order.items.all()} == {
        (hops.pk, 2, Decimal('5.99')),
        (malt.pk, 3, Decimal('2.50')),
    }
    hops.refresh_from_db()
    malt.refresh_from_db()
    assert (hops.stock, malt.stock) == (8, 0)


def test_item_price_does_not_follow_later_price_changes(user, product):
    order = _create(user, [OrderLine(product.pk, 1)])
    product.price = Decimal('99.00')
    product.save()
    assert order.items.get().price == Decimal('5.99')


def test_duplicate_lines_are_merged(user, product):
    order = _create(user, [OrderLine(product.pk, 1), OrderLine(product.pk, 2)])
    assert order.items.get().quantity == 3
    assert merge_lines([OrderLine(1, 1), OrderLine(2, 1), OrderLine(1, 4)]) == [
        OrderLine(1, 5),
        OrderLine(2, 1),
    ]


def test_order_is_atomic_when_one_line_lacks_stock(user, make_product):
    available = make_product(stock=5)
    scarce = make_product(stock=1)

    with pytest.raises(OrderError) as error:
        _create(user, [OrderLine(available.pk, 2), OrderLine(scarce.pk, 2)])

    assert 'Недостаточно товара' in error.value.messages[0]
    assert not Order.objects.exists()
    assert not OrderItem.objects.exists()
    available.refresh_from_db()
    scarce.refresh_from_db()
    assert (available.stock, scarce.stock) == (5, 1)


@pytest.mark.parametrize(
    ('lines_factory', 'message'),
    [
        (lambda p: [], 'хотя бы один товар'),
        (lambda p: [OrderLine(p.pk, 0)], 'больше нуля'),
        (lambda p: [OrderLine(p.pk, -1)], 'больше нуля'),
        (lambda p: [OrderLine(999_999, 1)], 'не найден'),
    ],
)
def test_invalid_lines_are_rejected(user, product, lines_factory, message):
    with pytest.raises(OrderError, match=message):
        _create(user, lines_factory(product))
    assert not Order.objects.exists()


def test_inactive_product_cannot_be_ordered(user, make_product):
    hidden = make_product(is_active=False)
    with pytest.raises(OrderError, match='снят с продажи'):
        _create(user, [OrderLine(hidden.pk, 1)])


def test_unknown_payment_method_and_blank_address(user, product):
    with pytest.raises(OrderError, match='способ оплаты'):
        _create(user, [OrderLine(product.pk, 1)], payment_method='bitcoin')
    with pytest.raises(OrderError, match='адрес'):
        _create(user, [OrderLine(product.pk, 1)], shipping_address='   ')


ALLOWED = [
    (S.PENDING, S.PAID),
    (S.PENDING, S.CANCELLED),
    (S.PAID, S.SHIPPED),
    (S.PAID, S.CANCELLED),
    (S.SHIPPED, S.DELIVERED),
]


@pytest.mark.parametrize(('start', 'target'), ALLOWED)
def test_allowed_transitions(user, product, make_order, start, target):
    order = make_order(user, [(product, 1)], status=start)
    change_order_status(order, target)
    order.refresh_from_db()
    assert order.status == target


@pytest.mark.parametrize(
    ('start', 'target'),
    [
        (start, target)
        for start in S.values
        for target in S.values
        if start != target and (start, target) not in ALLOWED
    ],
)
def test_forbidden_transitions(user, product, make_order, start, target):
    order = make_order(user, [(product, 1)], status=start)
    with pytest.raises(OrderError, match='Нельзя перевести'):
        change_order_status(order, target)
    order.refresh_from_db()
    assert order.status == start


@pytest.mark.parametrize('start', [S.PENDING, S.PAID])
def test_cancellation_restores_stock_once(user, product, make_order, start):
    order = make_order(user, [(product, 4)], status=start)
    product.refresh_from_db()
    assert product.stock == 6

    change_order_status(order, S.CANCELLED)
    product.refresh_from_db()
    assert product.stock == 10

    with pytest.raises(OrderError):
        change_order_status(order, S.CANCELLED)
    product.refresh_from_db()
    assert product.stock == 10


def test_customer_cancels_own_pending_order(user, product, make_order):
    order = make_order(user, [(product, 2)])
    cancel_order_by_customer(order, user)
    order.refresh_from_db()
    product.refresh_from_db()
    assert order.status == S.CANCELLED
    assert product.stock == 10


def test_customer_cannot_cancel_paid_order(user, product, make_order):
    order = make_order(user, [(product, 2)], status=S.PAID)
    with pytest.raises(OrderError, match='недоступно'):
        cancel_order_by_customer(order, user)
    order.refresh_from_db()
    assert order.status == S.PAID


def test_customer_cannot_cancel_someone_elses_order(user, other_user, product, make_order):
    order = make_order(user, [(product, 1)])
    with pytest.raises(OrderError, match='собственный'):
        cancel_order_by_customer(order, other_user)


def test_emails_are_sent_after_commit(
    user, product, settings, mailoutbox, django_capture_on_commit_callbacks
):
    settings.ORDER_NOTIFICATION_EMAIL = 'shop-admin@example.com'
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        order = _create(user, [OrderLine(product.pk, 2)])
    assert mailoutbox == []  # nothing is sent before the transaction commits

    for callback in callbacks:
        callback()
    assert [message.to for message in mailoutbox] == [[user.email], ['shop-admin@example.com']]
    assert f'№{order.pk}' in mailoutbox[0].subject
    assert '$11.98' in mailoutbox[0].body


def test_customer_without_email_only_admin_is_notified(
    make_user, product, mailoutbox, django_capture_on_commit_callbacks
):
    customer = make_user(email='')
    with django_capture_on_commit_callbacks(execute=True):
        _create(customer, [OrderLine(product.pk, 1)])
    assert len(mailoutbox) == 1


def test_failed_order_sends_no_email(user, product, mailoutbox, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True), pytest.raises(OrderError):
        _create(user, [OrderLine(product.pk, 100)])
    assert mailoutbox == []
