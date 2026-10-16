from typing import Any

from django import forms

from core.forms import StyledFormMixin
from orders.models import Order


class AddToCartForm(StyledFormMixin, forms.Form):
    quantity = forms.IntegerField(label='Количество', min_value=1, initial=1)

    def __init__(self, *args: Any, max_quantity: int | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if max_quantity is not None:
            self.fields['quantity'].widget.attrs['max'] = max(max_quantity, 1)


class CartUpdateForm(forms.Form):
    """Set an absolute quantity; zero removes the product from the cart."""

    quantity = forms.IntegerField(min_value=0)


class CheckoutForm(StyledFormMixin, forms.Form):
    full_name = forms.CharField(label='Получатель', max_length=150)
    phone = forms.CharField(label='Телефон', max_length=30)
    city = forms.CharField(label='Город', max_length=100)
    address = forms.CharField(label='Адрес доставки', widget=forms.Textarea)
    payment_method = forms.ChoiceField(
        label='Способ оплаты',
        choices=Order.PaymentMethod.choices,
        initial=Order.PaymentMethod.CARD,
        widget=forms.RadioSelect,
    )
    save_address = forms.BooleanField(label='Сохранить адрес в личном кабинете', required=False)

    def clean_phone(self) -> str:
        phone: str = self.cleaned_data['phone'].strip()
        digits = [char for char in phone if char.isdigit()]
        if len(digits) < 7 or any(not (c.isdigit() or c in '+-() ') for c in phone):
            raise forms.ValidationError('Введите корректный номер телефона.')
        return phone

    @property
    def shipping_address(self) -> str:
        return f'{self.cleaned_data["city"].strip()}, {self.cleaned_data["address"].strip()}'
