from django.http import HttpRequest

from orders.cart import Cart


def cart(request: HttpRequest) -> dict[str, int]:
    """Expose the number of units in the cart to every template (header badge)."""
    return {'cart_count': len(Cart(request.session))}
