from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

from orders.models import Order


def send_order_created_emails(order_id: int) -> None:
    """Notify the customer and the shop administrator about a new order.

    Called through `transaction.on_commit`, so it only runs once the order is
    actually saved.
    """
    order = Order.objects.select_related('user').prefetch_related('items__product').get(pk=order_id)
    context = {'order': order, 'items': order.items.all()}
    subject = f'Hop & Barley: заказ №{order.pk} оформлен'

    if order.user.email:
        send_mail(
            subject=subject,
            message=render_to_string('orders/emails/order_created_customer.txt', context),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[order.user.email],
        )
    send_mail(
        subject=f'Новый заказ №{order.pk}',
        message=render_to_string('orders/emails/order_created_admin.txt', context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[settings.ORDER_NOTIFICATION_EMAIL],
    )
