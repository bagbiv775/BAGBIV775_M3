from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.urls import reverse

from orders.models import Order
from users.models import Address

pytestmark = pytest.mark.django_db

CHECKOUT = reverse('orders:checkout')
ACCOUNT = reverse('users:account')

CHECKOUT_DATA = {
    'full_name': 'Иван Петров',
    'phone': '+7 700 123-45-67',
    'city': 'Алматы',
    'address': 'ул. Абая, 1',
    'payment_method': Order.PaymentMethod.CASH,
}


def put_in_cart(client, product, quantity=1):
    client.post(reverse('orders:cart_add', args=[product.pk]), {'quantity': quantity})


def messages_of(response):
    return [str(m) for m in get_messages(response.wsgi_request)]


class TestCheckout:
    def test_requires_login(self, client, product):
        put_in_cart(client, product)
        response = client.get(CHECKOUT)
        assert response.status_code == 302
        assert response.url == f'{reverse("users:login")}?next={CHECKOUT}'

    def test_empty_cart_redirects_to_cart(self, auth_client):
        response = auth_client.get(CHECKOUT)
        assert response.url == reverse('orders:cart')

    def test_form_lists_items_and_payment_methods(self, auth_client, product):
        put_in_cart(auth_client, product, 2)
        response = auth_client.get(CHECKOUT)
        assert response.status_code == 200
        assert '$11.98' in response.text
        for label in ('Банковская карта', 'Электронный кошелёк', 'Наличными при получении'):
            assert label in response.text

    def test_successful_checkout(
        self, auth_client, user, product, mailoutbox, django_capture_on_commit_callbacks
    ):
        put_in_cart(auth_client, product, 3)
        with django_capture_on_commit_callbacks(execute=True):
            response = auth_client.post(CHECKOUT, {**CHECKOUT_DATA, 'save_address': 'on'})

        order = Order.objects.get()
        assert response.url == reverse('orders:checkout_done', args=[order.pk])
        assert (order.user, order.status, order.payment_method) == (user, 'pending', 'cash')
        assert order.total_price == Decimal('17.97')
        assert order.shipping_address == 'Алматы, ул. Абая, 1'
        assert (order.contact_name, order.contact_phone) == ('Иван Петров', '+7 700 123-45-67')
        product.refresh_from_db()
        assert product.stock == 7
        assert auth_client.session.get('cart') is None
        assert f'Заказ №{order.pk} оформлен!' in messages_of(response)[-1]
        assert Address.objects.filter(user=user, city='Алматы').exists()
        assert len(mailoutbox) == 2

        done = auth_client.get(response.url)
        assert 'Спасибо' in done.text and '$17.97' in done.text

    def test_out_of_stock_at_checkout_keeps_cart_and_creates_nothing(self, auth_client, product):
        put_in_cart(auth_client, product, 5)
        product.stock = 2
        product.save()
        response = auth_client.post(CHECKOUT, CHECKOUT_DATA)
        assert response.url == reverse('orders:cart')
        assert not Order.objects.exists()
        assert auth_client.session['cart'] == {str(product.pk): 5}
        assert any('Недостаточно товара' in m for m in messages_of(response))

    @pytest.mark.parametrize(
        ('field', 'value'),
        [('phone', 'позвоните мне'), ('city', ''), ('payment_method', 'crypto'), ('full_name', '')],
    )
    def test_validation_errors(self, auth_client, product, field, value):
        put_in_cart(auth_client, product)
        response = auth_client.post(CHECKOUT, {**CHECKOUT_DATA, field: value})
        assert response.status_code == 200
        assert field in response.context['form'].errors
        assert not Order.objects.exists()

    def test_prefill_from_saved_address(self, auth_client, user, other_user, product):
        mine = Address.objects.create(
            user=user,
            label='Дом',
            full_name='Я',
            phone='+77000000000',
            city='Астана',
            address='пр. 1',
        )
        foreign = Address.objects.create(
            user=other_user, label='Чужой', full_name='Он', phone='1', city='Шымкент', address='x'
        )
        put_in_cart(auth_client, product)
        form = auth_client.get(CHECKOUT, {'address': mine.pk}).context['form']
        assert form.initial['city'] == 'Астана'
        form = auth_client.get(CHECKOUT, {'address': foreign.pk}).context['form']
        assert 'city' not in form.initial

    def test_done_page_is_private(self, client, user, other_user, product, make_order):
        order = make_order(user, [(product, 1)])
        client.force_login(other_user)
        assert client.get(reverse('orders:checkout_done', args=[order.pk])).status_code == 404


class TestAuth:
    def test_register_logs_in_and_keeps_cart(self, client, product):
        put_in_cart(client, product, 2)
        response = client.post(
            reverse('users:register'),
            {
                'username': 'newbie',
                'email': 'New@Example.com',
                'password1': 'Very-strong-42',
                'password2': 'Very-strong-42',
                'next': CHECKOUT,
            },
        )
        assert response.url == CHECKOUT
        user = User.objects.get(username='newbie')
        assert user.email == 'new@example.com'
        assert client.session['_auth_user_id'] == str(user.pk)
        assert client.session['cart'] == {str(product.pk): 2}

    def test_register_rejects_duplicate_email_and_weak_password(self, client, user):
        response = client.post(
            reverse('users:register'),
            {'username': 'x', 'email': user.email.upper(), 'password1': '123', 'password2': '123'},
        )
        errors = response.context['form'].errors
        assert 'email' in errors and 'password2' in errors

    def test_authenticated_user_is_redirected_from_register(self, auth_client):
        assert auth_client.get(reverse('users:register')).url == ACCOUNT

    def test_login_and_logout(self, client, user):
        assert client.get(reverse('users:login')).status_code == 200
        bad = client.post(reverse('users:login'), {'username': 'buyer', 'password': 'wrong'})
        assert bad.status_code == 200
        assert bad.context['form'].errors
        response = client.post(
            reverse('users:login'), {'username': 'buyer', 'password': 'Pass12345!'}
        )
        assert response.url == ACCOUNT
        response = client.post(reverse('users:logout'))
        assert response.status_code == 302
        assert '_auth_user_id' not in client.session

    def test_account_requires_login(self, client):
        response = client.get(ACCOUNT)
        assert response.url.startswith(reverse('users:login'))


class TestAccountOrders:
    def test_lists_only_own_orders_newest_first(
        self, auth_client, user, other_user, product, make_order
    ):
        first = make_order(user, [(product, 1)])
        second = make_order(user, [(product, 2)])
        make_order(other_user, [(product, 1)])
        orders = list(auth_client.get(ACCOUNT).context['orders'])
        assert orders == [second, first]
        assert orders[0].items_count == 2

    def test_filter_by_status(self, auth_client, user, product, make_order):
        make_order(user, [(product, 1)])
        paid = make_order(user, [(product, 1)], status=Order.Status.PAID)
        assert list(auth_client.get(ACCOUNT, {'status': 'paid'}).context['orders']) == [paid]

    def test_order_detail_only_for_owner(self, auth_client, user, other_user, product, make_order):
        mine = make_order(user, [(product, 2)])
        foreign = make_order(other_user, [(product, 1)])
        response = auth_client.get(reverse('orders:detail', args=[mine.pk]))
        assert response.status_code == 200
        assert 'Отменить заказ' in response.text
        assert auth_client.get(reverse('orders:detail', args=[foreign.pk])).status_code == 404

    def test_cancel_pending_order(self, auth_client, user, product, make_order):
        order = make_order(user, [(product, 4)])
        response = auth_client.post(reverse('orders:cancel', args=[order.pk]))
        order.refresh_from_db()
        product.refresh_from_db()
        assert order.status == Order.Status.CANCELLED
        assert product.stock == 10
        assert messages_of(response) == [f'Заказ №{order.pk} отменён.']

    def test_cannot_cancel_paid_or_foreign_order(
        self, auth_client, user, other_user, product, make_order
    ):
        paid = make_order(user, [(product, 1)], status=Order.Status.PAID)
        response = auth_client.post(reverse('orders:cancel', args=[paid.pk]))
        paid.refresh_from_db()
        assert paid.status == Order.Status.PAID
        assert 'недоступно' in messages_of(response)[0]
        assert (
            'Отменить заказ' not in auth_client.get(reverse('orders:detail', args=[paid.pk])).text
        )

        foreign = make_order(other_user, [(product, 1)])
        assert auth_client.post(reverse('orders:cancel', args=[foreign.pk])).status_code == 404
        foreign.refresh_from_db()
        assert foreign.status == Order.Status.PENDING


class TestProfile:
    def test_update_profile(self, auth_client, user, other_user):
        response = auth_client.post(
            reverse('users:profile'),
            {'first_name': 'Иван', 'last_name': 'Петров', 'email': 'ivan@example.com'},
        )
        assert response.url == reverse('users:profile')
        user.refresh_from_db()
        assert (user.first_name, user.email) == ('Иван', 'ivan@example.com')

        taken = auth_client.post(
            reverse('users:profile'), {'first_name': '', 'last_name': '', 'email': other_user.email}
        )
        assert 'email' in taken.context['form'].errors

    def test_change_password(self, auth_client, user):
        response = auth_client.post(
            reverse('users:password_change'),
            {
                'old_password': 'Pass12345!',
                'new_password1': 'Brand-new-pass-77',
                'new_password2': 'Brand-new-pass-77',
            },
        )
        assert response.url == ACCOUNT
        user.refresh_from_db()
        assert user.check_password('Brand-new-pass-77')

    def test_addresses_crud_and_isolation(self, auth_client, user, other_user):
        data = {
            'label': 'Дом',
            'full_name': 'Я',
            'phone': '+7700',
            'city': 'Алматы',
            'address': 'Абая 1',
        }
        auth_client.post(reverse('users:address_add'), data)
        address = Address.objects.get(user=user)
        assert 'Дом' in auth_client.get(reverse('users:addresses')).text

        auth_client.post(
            reverse('users:address_edit', args=[address.pk]), {**data, 'label': 'Работа'}
        )
        address.refresh_from_db()
        assert address.label == 'Работа'

        foreign = Address.objects.create(user=other_user, **data)
        assert auth_client.get(reverse('users:address_edit', args=[foreign.pk])).status_code == 404
        assert (
            auth_client.post(reverse('users:address_delete', args=[foreign.pk])).status_code == 404
        )

        assert (
            auth_client.get(reverse('users:address_delete', args=[address.pk])).status_code == 200
        )
        auth_client.post(reverse('users:address_delete', args=[address.pk]))
        assert not Address.objects.filter(user=user).exists()
