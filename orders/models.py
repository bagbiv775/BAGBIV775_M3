from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.urls import reverse

from core.models import TimeStampedModel


class Order(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Ожидает оплаты'
        PAID = 'paid', 'Оплачен'
        SHIPPED = 'shipped', 'Отправлен'
        DELIVERED = 'delivered', 'Доставлен'
        CANCELLED = 'cancelled', 'Отменён'

    class PaymentMethod(models.TextChoices):
        CARD = 'card', 'Банковская карта'
        WALLET = 'wallet', 'Электронный кошелёк'
        CASH = 'cash', 'Наличными при получении'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='orders',
        verbose_name='покупатель',
    )
    status = models.CharField(
        'статус', max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    payment_method = models.CharField('способ оплаты', max_length=20, choices=PaymentMethod.choices)
    total_price = models.DecimalField(
        'сумма',
        max_digits=12,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    contact_name = models.CharField('получатель', max_length=150, blank=True)
    contact_phone = models.CharField('телефон', max_length=30, blank=True)
    shipping_address = models.TextField('адрес доставки')

    class Meta:
        verbose_name = 'заказ'
        verbose_name_plural = 'заказы'
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                condition=Q(total_price__gte=0), name='order_total_price_non_negative'
            ),
        ]

    def __str__(self) -> str:
        return f'Заказ №{self.pk}'

    def get_absolute_url(self) -> str:
        return reverse('orders:detail', kwargs={'pk': self.pk})

    @property
    def allowed_next_statuses(self) -> tuple[str, ...]:
        return STATUS_TRANSITIONS.get(self.status, ())

    def can_change_status_to(self, new_status: str) -> bool:
        return new_status in self.allowed_next_statuses

    @property
    def can_be_cancelled_by_customer(self) -> bool:
        return self.status == self.Status.PENDING


STATUS_TRANSITIONS: dict[str, tuple[str, ...]] = {
    Order.Status.PENDING: (Order.Status.PAID, Order.Status.CANCELLED),
    Order.Status.PAID: (Order.Status.SHIPPED, Order.Status.CANCELLED),
    Order.Status.SHIPPED: (Order.Status.DELIVERED,),
    Order.Status.DELIVERED: (),
    Order.Status.CANCELLED: (),
}

# Orders in these statuses count towards product popularity and analytics revenue.
SOLD_STATUSES: tuple[str, ...] = (
    Order.Status.PAID,
    Order.Status.SHIPPED,
    Order.Status.DELIVERED,
)


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name='items', verbose_name='заказ'
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        related_name='order_items',
        verbose_name='товар',
    )
    quantity = models.IntegerField('количество', validators=[MinValueValidator(1)])
    price = models.DecimalField(
        'цена за единицу',
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        help_text='Цена товара на момент оформления заказа.',
    )

    class Meta:
        verbose_name = 'позиция заказа'
        verbose_name_plural = 'позиции заказа'
        constraints = [
            models.UniqueConstraint(fields=['order', 'product'], name='unique_order_product'),
            models.CheckConstraint(
                condition=Q(quantity__gt=0), name='order_item_quantity_positive'
            ),
            models.CheckConstraint(condition=Q(price__gte=0), name='order_item_price_non_negative'),
        ]

    def __str__(self) -> str:
        return f'{self.product} × {self.quantity}'

    @property
    def line_total(self) -> Decimal:
        return self.price * self.quantity
