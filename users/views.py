from collections.abc import Mapping
from typing import Any

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import QuerySet, Sum
from django.http import HttpRequest, HttpResponse
from django.http.response import HttpResponseBase
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from core.auth import authenticated_user
from orders.models import Order
from users.forms import (
    AddressForm,
    LoginForm,
    OrderHistoryFilterForm,
    ProfileForm,
    RegistrationForm,
    StyledPasswordChangeForm,
)
from users.models import Address


class RegisterView(CreateView[User, RegistrationForm]):
    template_name = 'users/register.html'
    form_class = RegistrationForm

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
        if request.user.is_authenticated:
            return redirect('users:account')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form: RegistrationForm) -> HttpResponse:
        user = form.save()
        # login() keeps the session data, so the anonymous cart survives sign-up.
        login(self.request, user)
        messages.success(
            self.request, f'Добро пожаловать, {user.username}! Регистрация прошла успешно.'
        )
        next_url = self.request.POST.get('next', '')
        if url_has_allowed_host_and_scheme(next_url, allowed_hosts={self.request.get_host()}):
            return redirect(next_url)
        return redirect('users:account')


class LoginView(SuccessMessageMixin, auth_views.LoginView):
    template_name = 'users/login.html'
    authentication_form = LoginForm
    redirect_authenticated_user = True
    success_message = 'Вы вошли в аккаунт.'


class LogoutView(auth_views.LogoutView):
    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        response = super().post(request, *args, **kwargs)
        messages.info(request, 'Вы вышли из аккаунта.')
        return response


class AccountView(LoginRequiredMixin, ListView):
    """Account home: the customer's own order history."""

    template_name = 'users/account.html'
    context_object_name = 'orders'
    paginate_by = 10

    def get_queryset(self) -> QuerySet[Order]:
        queryset = (
            Order.objects.filter(user=authenticated_user(self.request))
            .annotate(items_count=Sum('items__quantity'))
            .order_by('-created_at', '-pk')
        )
        self.filter_form = OrderHistoryFilterForm(self.request.GET or None)
        if self.filter_form.is_valid() and self.filter_form.cleaned_data['status']:
            queryset = queryset.filter(status=self.filter_form.cleaned_data['status'])
        return queryset

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context['filter_form'] = self.filter_form
        context['active_tab'] = 'orders'
        return context


class ProfileView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    template_name = 'users/profile.html'
    form_class = ProfileForm
    success_url = reverse_lazy('users:profile')
    success_message = 'Данные профиля сохранены.'
    extra_context = {'active_tab': 'profile'}

    def get_object(self, queryset: QuerySet[User] | None = None) -> User:
        return authenticated_user(self.request)


class PasswordChangeView(SuccessMessageMixin, auth_views.PasswordChangeView):
    template_name = 'users/password_change.html'
    form_class = StyledPasswordChangeForm
    success_url = reverse_lazy('users:account')
    success_message = 'Пароль изменён.'
    extra_context = {'active_tab': 'password'}


class AddressQuerysetMixin(LoginRequiredMixin):
    request: HttpRequest
    extra_context: Mapping[str, Any] | None = {'active_tab': 'addresses'}

    def get_queryset(self) -> QuerySet[Address]:
        return Address.objects.filter(user=authenticated_user(self.request))


class AddressListView(AddressQuerysetMixin, ListView):
    template_name = 'users/address_list.html'
    context_object_name = 'addresses'


class AddressCreateView(
    AddressQuerysetMixin, SuccessMessageMixin, CreateView[Address, AddressForm]
):
    template_name = 'users/address_form.html'
    form_class = AddressForm
    success_url = reverse_lazy('users:addresses')
    success_message = 'Адрес сохранён.'

    def form_valid(self, form: AddressForm) -> HttpResponse:
        form.instance.user = authenticated_user(self.request)
        return super().form_valid(form)


class AddressUpdateView(AddressQuerysetMixin, SuccessMessageMixin, UpdateView):
    template_name = 'users/address_form.html'
    form_class = AddressForm
    success_url = reverse_lazy('users:addresses')
    success_message = 'Адрес обновлён.'


class AddressDeleteView(AddressQuerysetMixin, SuccessMessageMixin, DeleteView):
    template_name = 'users/address_confirm_delete.html'
    success_url = reverse_lazy('users:addresses')
    success_message = 'Адрес удалён.'
