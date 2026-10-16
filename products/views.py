from typing import Any

from django.db.models import Q
from django.views.generic import DetailView, ListView

from orders.cart import Cart
from orders.forms import AddToCartForm
from products.forms import CatalogFilterForm
from products.models import Product, ProductQuerySet
from reviews.forms import ReviewForm
from reviews.services import review_denial_reason

SORT_ORDERING = {
    CatalogFilterForm.SORT_NEW: ['-created_at', '-pk'],
    CatalogFilterForm.SORT_PRICE_ASC: ['price', 'pk'],
    CatalogFilterForm.SORT_PRICE_DESC: ['-price', 'pk'],
    CatalogFilterForm.SORT_POPULAR: ['-popularity', '-created_at', '-pk'],
}


class ProductListView(ListView):
    """Catalog with search, category and price filters, sorting and pagination."""

    template_name = 'products/catalog.html'
    context_object_name = 'products'
    paginate_by = 9

    def get_queryset(self) -> ProductQuerySet:
        self.filter_form = CatalogFilterForm(self.request.GET or None)
        queryset = Product.objects.active().select_related('category').with_rating()
        sort = CatalogFilterForm.SORT_NEW

        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            if data['q']:
                queryset = queryset.filter(
                    Q(name__icontains=data['q']) | Q(description__icontains=data['q'])
                )
            if data['category']:
                queryset = queryset.filter(category=data['category'])
            if data['min_price'] is not None:
                queryset = queryset.filter(price__gte=data['min_price'])
            if data['max_price'] is not None:
                queryset = queryset.filter(price__lte=data['max_price'])
            sort = data['sort'] or sort

        if sort == CatalogFilterForm.SORT_POPULAR:
            queryset = queryset.with_popularity()
        self.current_sort = sort
        return queryset.order_by(*SORT_ORDERING[sort])

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context['filter_form'] = self.filter_form
        context['current_sort'] = self.current_sort
        context['sort_choices'] = CatalogFilterForm.SORT_CHOICES
        return context


class ProductDetailView(DetailView):
    template_name = 'products/product_detail.html'
    context_object_name = 'product'

    def get_queryset(self) -> ProductQuerySet:
        return Product.objects.active().select_related('category').with_rating()

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        product: Product = self.object
        user = self.request.user
        denial_reason = review_denial_reason(user, product)

        context['reviews'] = product.reviews.select_related('user')
        context['review_denial_reason'] = denial_reason
        if denial_reason is None:
            context['review_form'] = ReviewForm(user=user, product=product)
        context['cart_quantity'] = Cart(self.request.session).quantity_of(product.pk)
        context['add_to_cart_form'] = AddToCartForm(max_quantity=product.stock)
        context['related_products'] = (
            Product.objects.active()
            .filter(category=product.category, stock__gt=0)
            .exclude(pk=product.pk)[:3]
        )
        return context
