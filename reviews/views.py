from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.http.response import HttpResponseBase
from django.shortcuts import get_object_or_404
from django.views.generic import CreateView

from products.models import Product
from reviews.forms import ReviewForm
from reviews.models import Review


class ReviewCreateView(LoginRequiredMixin, CreateView[Review, ReviewForm]):
    """Accept a review form posted from the product page.

    The result (success or the reason for rejection) is reported through the
    message framework and the user is sent back to the product page.
    """

    form_class = ReviewForm
    http_method_names = ['post']

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
        self.product = get_object_or_404(Product.objects.active(), slug=kwargs['slug'])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs.update(user=self.request.user, product=self.product)
        return kwargs

    def form_valid(self, form: ReviewForm) -> HttpResponse:
        try:
            form.save()
        except IntegrityError:
            messages.error(self.request, 'Вы уже оставили отзыв на этот товар.')
        else:
            messages.success(self.request, 'Спасибо! Ваш отзыв опубликован.')
        return self._back_to_product()

    def form_invalid(self, form: ReviewForm) -> HttpResponse:
        for errors in form.errors.values():
            for error in errors:
                messages.error(self.request, f'Отзыв не принят: {error}')
        return self._back_to_product()

    def _back_to_product(self) -> HttpResponse:
        return HttpResponseRedirect(f'{self.product.get_absolute_url()}#reviews')
