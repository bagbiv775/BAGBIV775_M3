from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.http.response import HttpResponseBase
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import DetailView, FormView, TemplateView

from core.auth import authenticated_user
from orders.cart import Cart, CartError
from orders.forms import AddToCartForm, CartUpdateForm, CheckoutForm
from orders.models import Order
from orders.services import OrderError, cancel_order_by_customer, create_order
from products.models import Product
from users.models import Address


class CartDetailView(TemplateView):
    template_name = 'orders/cart.html'

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        items = Cart(self.request.session).items()
        context['items'] = items
        context['total'] = Cart.total_of(items)
        context['has_problems'] = any(item.problem for item in items)
        return context


class CartAddView(View):
    def post(self, request: HttpRequest, product_id: int) -> HttpResponse:
        product = get_object_or_404(Product.objects.active(), pk=product_id)
        form = AddToCartForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Укажите количество не меньше 1.')
        else:
            try:
                quantity = Cart(request.session).add(product, form.cleaned_data['quantity'])
            except CartError as error:
                messages.error(request, str(error))
            else:
                messages.success(
                    request, f'«{product.name}» добавлен в корзину (в корзине: {quantity} шт.).'
                )
        return redirect(_safe_next_url(request, default=product.get_absolute_url()))


class CartUpdateView(View):
    def post(self, request: HttpRequest, product_id: int) -> HttpResponse:
        product = get_object_or_404(Product, pk=product_id)
        form = CartUpdateForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Некорректное количество.')
            return redirect('orders:cart')
        try:
            quantity = Cart(request.session).set(product, form.cleaned_data['quantity'])
        except CartError as error:
            messages.error(request, str(error))
        else:
            if quantity:
                messages.success(request, f'Количество «{product.name}» изменено: {quantity} шт.')
            else:
                messages.info(request, f'«{product.name}» удалён из корзины.')
        return redirect('orders:cart')


class CartRemoveView(View):
    def post(self, request: HttpRequest, product_id: int) -> HttpResponse:
        Cart(request.session).remove(product_id)
        messages.info(request, 'Товар удалён из корзины.')
        return redirect('orders:cart')


class CheckoutView(LoginRequiredMixin, FormView):
    template_name = 'orders/checkout.html'
    form_class = CheckoutForm

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
        if request.user.is_authenticated and not Cart(request.session):
            messages.info(request, 'Корзина пуста — добавьте товары, чтобы оформить заказ.')
            return redirect('orders:cart')
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self) -> dict[str, Any]:
        """Prefill the form from a saved address chosen via `?address=<id>`."""
        initial = super().get_initial()
        user = authenticated_user(self.request)
        initial['full_name'] = user.get_full_name()
        address_id = self.request.GET.get('address')
        if address_id and address_id.isdigit():
            address = Address.objects.filter(user=user, pk=address_id).first()
            if address:
                initial.update(
                    full_name=address.full_name,
                    phone=address.phone,
                    city=address.city,
                    address=address.address,
                )
        return initial

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        items = Cart(self.request.session).items()
        context['items'] = items
        context['total'] = Cart.total_of(items)
        context['saved_addresses'] = Address.objects.filter(user=authenticated_user(self.request))
        return context

    def form_valid(self, form: CheckoutForm) -> HttpResponse:
        cart = Cart(self.request.session)
        user = authenticated_user(self.request)
        data = form.cleaned_data
        try:
            order = create_order(
                user=user,
                lines=cart.as_order_lines(),
                shipping_address=form.shipping_address,
                payment_method=data['payment_method'],
                contact_name=data['full_name'],
                contact_phone=data['phone'],
            )
        except OrderError as error:
            for message in error.messages:
                messages.error(self.request, message)
            messages.error(self.request, 'Заказ не оформлен. Проверьте корзину и попробуйте снова.')
            return redirect('orders:cart')

        if data['save_address']:
            Address.objects.get_or_create(
                user=user,
                full_name=data['full_name'],
                phone=data['phone'],
                city=data['city'],
                address=data['address'],
                defaults={'label': data['city']},
            )
        cart.clear()
        messages.success(
            self.request, f'Заказ №{order.pk} оформлен! Мы сообщим, когда он будет оплачен.'
        )
        return redirect('orders:checkout_done', pk=order.pk)


class CustomerOrderMixin(LoginRequiredMixin):
    """Restrict order views to the current user's orders (others get 404)."""

    request: HttpRequest

    def get_queryset(self) -> QuerySet[Order]:
        return Order.objects.filter(user=authenticated_user(self.request)).prefetch_related(
            'items__product'
        )


class CheckoutDoneView(CustomerOrderMixin, DetailView):
    template_name = 'orders/checkout_done.html'
    context_object_name = 'order'


class OrderDetailView(CustomerOrderMixin, DetailView):
    template_name = 'orders/order_detail.html'
    context_object_name = 'order'


class OrderCancelView(CustomerOrderMixin, View):
    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        order = get_object_or_404(self.get_queryset(), pk=pk)
        try:
            cancel_order_by_customer(order, authenticated_user(request))
        except OrderError as error:
            messages.error(request, ' '.join(error.messages))
        else:
            messages.success(request, f'Заказ №{order.pk} отменён.')
        return redirect('orders:detail', pk=order.pk)


def _safe_next_url(request: HttpRequest, default: str) -> str:
    next_url = request.POST.get('next') or request.GET.get('next')
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return next_url
    return default or reverse('orders:cart')
