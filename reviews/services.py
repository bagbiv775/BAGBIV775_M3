from django.contrib.auth.models import AnonymousUser, User

from orders.models import Order, OrderItem
from products.models import Product
from reviews.models import Review


def has_received_product(user: User, product: Product) -> bool:
    return OrderItem.objects.filter(
        order__user=user,
        order__status=Order.Status.DELIVERED,
        product=product,
    ).exists()


def review_denial_reason(user: User | AnonymousUser, product: Product) -> str | None:
    """Explain why `user` cannot review `product`, or return None if they can.

    Shared by the web form and the REST API serializer.
    """
    if not isinstance(user, User) or not user.is_authenticated:
        return 'Войдите в аккаунт, чтобы оставить отзыв.'
    if Review.objects.filter(user=user, product=product).exists():
        return 'Вы уже оставили отзыв на этот товар.'
    if not has_received_product(user, product):
        return 'Отзыв можно оставить только на товар из доставленного заказа.'
    return None
