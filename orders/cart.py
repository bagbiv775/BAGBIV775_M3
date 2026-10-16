"""Shopping cart stored in the Django session (web interface only).

The session holds only product ids and quantities. Prices, names and stock are
always read from the database, so the cart never shows stale prices.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings
from django.contrib.sessions.backends.base import SessionBase

from orders.services import OrderLine
from products.models import Product


class CartError(Exception):
    """The requested cart change is not possible (inactive product, no stock)."""


@dataclass(frozen=True)
class CartItem:
    product: Product
    quantity: int

    @property
    def line_total(self) -> Decimal:
        return self.product.price * self.quantity

    @property
    def problem(self) -> str | None:
        """Why this line cannot be ordered right now, or None if it can."""
        if not self.product.is_active:
            return 'Товар снят с продажи.'
        if self.product.stock <= 0:
            return 'Товара нет в наличии.'
        if self.quantity > self.product.stock:
            return f'В наличии только {self.product.stock} шт.'
        return None


class Cart:
    def __init__(self, session: SessionBase) -> None:
        self.session = session
        stored = session.get(settings.CART_SESSION_KEY) or {}
        self._quantities: dict[str, int] = {str(k): int(v) for k, v in stored.items()}

    def __len__(self) -> int:
        """Total number of units in the cart (shown in the header badge)."""
        return sum(self._quantities.values())

    def __bool__(self) -> bool:
        return bool(self._quantities)

    def quantity_of(self, product_id: int) -> int:
        return self._quantities.get(str(product_id), 0)

    def add(self, product: Product, quantity: int = 1) -> int:
        """Add `quantity` units on top of what is already in the cart."""
        if quantity <= 0:
            raise CartError('Количество должно быть больше нуля.')
        return self.set(product, self.quantity_of(product.pk) + quantity)

    def set(self, product: Product, quantity: int) -> int:
        """Replace the quantity of a product; zero removes it from the cart."""
        if quantity <= 0:
            self.remove(product.pk)
            return 0
        if not product.is_active:
            raise CartError(f'Товар «{product.name}» снят с продажи.')
        if quantity > product.stock:
            raise CartError(
                f'Нельзя добавить {quantity} шт. товара «{product.name}»: '
                f'в наличии {product.stock} шт.'
            )
        self._quantities[str(product.pk)] = quantity
        self._save()
        return quantity

    def remove(self, product_id: int) -> None:
        if self._quantities.pop(str(product_id), None) is not None:
            self._save()

    def clear(self) -> None:
        self._quantities = {}
        self.session.pop(settings.CART_SESSION_KEY, None)
        self.session.modified = True

    def items(self) -> list[CartItem]:
        """Cart lines with fresh product data; products deleted meanwhile are dropped."""
        products = Product.objects.select_related('category').in_bulk(
            [int(pk) for pk in self._quantities]
        )
        items = [
            CartItem(product=products[int(pk)], quantity=quantity)
            for pk, quantity in self._quantities.items()
            if int(pk) in products
        ]
        if len(items) != len(self._quantities):
            self._quantities = {str(item.product.pk): item.quantity for item in items}
            self._save()
        return items

    @staticmethod
    def total_of(items: list[CartItem]) -> Decimal:
        return sum((item.line_total for item in items), Decimal('0'))

    def as_order_lines(self) -> list[OrderLine]:
        return [OrderLine(int(pk), quantity) for pk, quantity in self._quantities.items()]

    def _save(self) -> None:
        self.session[settings.CART_SESSION_KEY] = self._quantities
        self.session.modified = True
