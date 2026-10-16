"""Order business rules shared by the web interface, the REST API and the admin.

Views, serializers and admin actions never change order status or stock
directly; they call the functions in this module instead.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import F

from orders.models import STATUS_TRANSITIONS, Order, OrderItem
from orders.notifications import send_order_created_emails
from products.models import Product


class OrderError(Exception):
    """A business rule violation. `messages` are safe to show to the customer."""

    def __init__(self, *messages: str) -> None:
        super().__init__(' '.join(messages))
        self.messages = list(messages)


@dataclass(frozen=True)
class OrderLine:
    product_id: int
    quantity: int


def merge_lines(lines: Iterable[OrderLine]) -> list[OrderLine]:
    """Combine lines that refer to the same product, preserving first-seen order."""
    totals: dict[int, int] = {}
    for line in lines:
        totals[line.product_id] = totals.get(line.product_id, 0) + line.quantity
    return [OrderLine(product_id, quantity) for product_id, quantity in totals.items()]


def create_order(
    *,
    user: User,
    lines: Iterable[OrderLine],
    shipping_address: str,
    payment_method: str,
    contact_name: str = '',
    contact_phone: str = '',
) -> Order:
    """Create a pending order, its items and reserve stock in one transaction.

    Prices are always read from the database and copied into `OrderItem.price`.
    If any line is invalid nothing is written and `OrderError` is raised.
    """
    merged = merge_lines(lines)
    if not merged:
        raise OrderError('Заказ должен содержать хотя бы один товар.')
    if payment_method not in Order.PaymentMethod.values:
        raise OrderError('Выбран неизвестный способ оплаты.')
    if not shipping_address.strip():
        raise OrderError('Укажите адрес доставки.')

    with transaction.atomic():
        # Lock the product rows in a stable order so that concurrent checkouts
        # cannot oversell the same stock or deadlock each other.
        products = (
            Product.objects.select_for_update()
            .order_by('pk')
            .in_bulk([line.product_id for line in merged])
        )
        _validate_lines(merged, products)

        items = [
            OrderItem(
                product=products[line.product_id],
                quantity=line.quantity,
                price=products[line.product_id].price,
            )
            for line in merged
        ]
        total = sum((item.line_total for item in items), Decimal('0'))

        order = Order.objects.create(
            user=user,
            status=Order.Status.PENDING,
            payment_method=payment_method,
            total_price=total,
            shipping_address=shipping_address.strip(),
            contact_name=contact_name.strip(),
            contact_phone=contact_phone.strip(),
        )
        for item in items:
            item.order = order
        OrderItem.objects.bulk_create(items)

        for line in merged:
            Product.objects.filter(pk=line.product_id).update(stock=F('stock') - line.quantity)

        order_id = order.pk
        transaction.on_commit(lambda: send_order_created_emails(order_id))
    return order


def _validate_lines(lines: list[OrderLine], products: dict[int, Product]) -> None:
    errors: list[str] = []
    for line in lines:
        product = products.get(line.product_id)
        if product is None:
            errors.append(f'Товар #{line.product_id} не найден.')
        elif not product.is_active:
            errors.append(f'Товар «{product.name}» снят с продажи.')
        elif line.quantity <= 0:
            errors.append(f'Количество товара «{product.name}» должно быть больше нуля.')
        elif line.quantity > product.stock:
            errors.append(
                f'Недостаточно товара «{product.name}»: '
                f'запрошено {line.quantity}, в наличии {product.stock}.'
            )
    if errors:
        raise OrderError(*errors)


def change_order_status(
    order: Order,
    new_status: str,
    *,
    allowed_from: Iterable[str] | None = None,
) -> Order:
    """Move an order to `new_status` if the transition is allowed.

    The order row is locked, so a second, concurrent cancellation sees the
    already-cancelled status and is rejected instead of restoring stock twice.
    `allowed_from` narrows the statuses the change may start from (used for
    customer cancellations, which are only possible while the order is pending).
    """
    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        current = locked.status
        if allowed_from is not None and current not in set(allowed_from):
            raise OrderError(
                f'Действие недоступно для заказа в статусе «{locked.get_status_display()}».'
            )
        if new_status not in STATUS_TRANSITIONS.get(current, ()):
            raise OrderError(
                f'Нельзя перевести заказ №{locked.pk} из статуса '
                f'«{locked.get_status_display()}» в «{Order.Status(new_status).label}».'
            )
        if new_status == Order.Status.CANCELLED:
            _restore_stock(locked)
        locked.status = new_status
        locked.save(update_fields=['status', 'updated_at'])

    order.status = locked.status
    order.updated_at = locked.updated_at
    return order


def cancel_order_by_customer(order: Order, user: User) -> Order:
    """Cancel the customer's own order; only pending orders can be cancelled."""
    if order.user_id != user.pk:
        raise OrderError('Можно отменить только собственный заказ.')
    return change_order_status(order, Order.Status.CANCELLED, allowed_from=(Order.Status.PENDING,))


def _restore_stock(order: Order) -> None:
    # Updating in product id order keeps row-lock acquisition consistent with
    # create_order(), which also locks products ordered by primary key.
    items = order.items.order_by('product_id').values_list('product_id', 'quantity')
    for product_id, quantity in items:
        Product.objects.filter(pk=product_id).update(stock=F('stock') + quantity)
