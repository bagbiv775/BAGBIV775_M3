from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def money(value: object) -> str:
    """Format a price as `$1,234.50` regardless of the active locale."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return ''
    return f'${amount:,.2f}'


@register.filter
def stars(rating: float | int | None) -> list[bool]:
    """Five booleans for rendering filled/empty rating stars."""
    rounded = round(rating or 0)
    return [index < rounded for index in range(5)]
