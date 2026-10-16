from __future__ import annotations

from typing import Any

from django import forms
from django.contrib.auth.models import AnonymousUser, User

from core.forms import StyledFormMixin
from products.models import Product
from reviews.models import MAX_RATING, MIN_RATING, Review
from reviews.services import review_denial_reason

RATING_CHOICES = [(value, str(value)) for value in range(MAX_RATING, MIN_RATING - 1, -1)]


class ReviewForm(StyledFormMixin, forms.ModelForm[Review]):
    rating = forms.TypedChoiceField(
        label='Оценка',
        choices=RATING_CHOICES,
        coerce=int,
        widget=forms.RadioSelect,
    )

    class Meta:
        model = Review
        fields = ['rating', 'comment']
        widgets = {'comment': forms.Textarea(attrs={'placeholder': 'Поделитесь впечатлениями'})}

    def __init__(
        self,
        *args: Any,
        user: User | AnonymousUser,
        product: Product,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.user = user
        self.product = product

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        reason = review_denial_reason(self.user, self.product)
        if reason:
            raise forms.ValidationError(reason)
        return cleaned

    def save(self, commit: bool = True) -> Review:
        if not isinstance(self.user, User):
            raise ValueError('Only an authenticated user can save a review.')
        review = super().save(commit=False)
        review.user = self.user
        review.product = self.product
        if commit:
            review.save()
        return review
