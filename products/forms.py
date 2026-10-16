from decimal import Decimal
from typing import Any

from django import forms

from core.forms import StyledFormMixin
from products.models import Category


class CatalogFilterForm(StyledFormMixin, forms.Form):
    SORT_NEW = 'new'
    SORT_PRICE_ASC = 'price_asc'
    SORT_PRICE_DESC = 'price_desc'
    SORT_POPULAR = 'popular'
    SORT_CHOICES = [
        (SORT_NEW, 'Новинки'),
        (SORT_PRICE_ASC, 'Цена ↑'),
        (SORT_PRICE_DESC, 'Цена ↓'),
        (SORT_POPULAR, 'Популярные'),
    ]

    q = forms.CharField(
        label='Поиск',
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={'placeholder': 'Название или описание'}),
    )
    category = forms.ModelChoiceField(
        label='Категория',
        queryset=Category.objects.all(),
        to_field_name='slug',
        required=False,
        empty_label='Все категории',
        widget=forms.RadioSelect,
    )
    min_price = forms.DecimalField(
        label='Цена от', required=False, min_value=Decimal('0'), decimal_places=2
    )
    max_price = forms.DecimalField(
        label='Цена до', required=False, min_value=Decimal('0'), decimal_places=2
    )
    sort = forms.ChoiceField(label='Сортировка', choices=SORT_CHOICES, required=False)

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        min_price, max_price = cleaned.get('min_price'), cleaned.get('max_price')
        if min_price is not None and max_price is not None and min_price > max_price:
            raise forms.ValidationError('Минимальная цена не может быть больше максимальной.')
        return cleaned
