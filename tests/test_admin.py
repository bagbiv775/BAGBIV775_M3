import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

from orders.models import Order
from reviews.models import Review
from users.models import Address

pytestmark = pytest.mark.django_db


def change_url(order):
    return reverse('admin:orders_order_change', args=[order.pk])


def order_form_data(order, status):
    return {
        'status': status,
        'contact_name': order.contact_name,
        'contact_phone': order.contact_phone,
        'shipping_address': order.shipping_address,
        'items-TOTAL_FORMS': order.items.count(),
        'items-INITIAL_FORMS': order.items.count(),
        'items-MIN_NUM_FORMS': 0,
        'items-MAX_NUM_FORMS': 1000,
        **{f'items-{i}-id': item.pk for i, item in enumerate(order.items.all())},
        **{f'items-{i}-order': order.pk for i, _ in enumerate(order.items.all())},
        '_save': 'Сохранить',
    }


def test_admin_requires_staff(client, user):
    client.force_login(user)
    response = client.get(reverse('admin:orders_order_changelist'))
    assert response.status_code == 302


@pytest.mark.parametrize(
    'name',
    [
        'admin:products_category_changelist',
        'admin:products_product_changelist',
        'admin:orders_order_changelist',
        'admin:reviews_review_changelist',
        'admin:users_address_changelist',
        'admin:auth_user_changelist',
        'admin:orders_order_analytics',
    ],
)
def test_admin_pages_render(admin_web_client, product, user, make_order, name):
    order = make_order(user, [(product, 1)], status=Order.Status.DELIVERED)
    Review.objects.create(user=user, product=product, rating=5, comment='ok')
    Address.objects.create(user=user, label='Дом', full_name='Я', phone='1', city='А', address='Б')
    response = admin_web_client.get(reverse(name), {'q': 'a'} if 'changelist' in name else {})
    assert response.status_code == 200
    assert admin_web_client.get(change_url(order)).status_code == 200
    assert (
        admin_web_client.get(
            reverse('admin:products_product_change', args=[product.pk])
        ).status_code
        == 200
    )


def test_orders_cannot_be_added_or_deleted(admin_web_client, user, product, make_order):
    order = make_order(user, [(product, 1)])
    assert admin_web_client.get(reverse('admin:orders_order_add')).status_code == 403
    assert (
        admin_web_client.get(reverse('admin:orders_order_delete', args=[order.pk])).status_code
        == 403
    )
    changelist = admin_web_client.get(reverse('admin:orders_order_changelist'))
    assert 'delete_selected' not in changelist.text


def test_status_choices_follow_transitions(admin_web_client, user, product, make_order):
    pending = make_order(user, [(product, 1)])
    form = admin_web_client.get(change_url(pending)).context['adminform'].form
    assert [value for value, _ in form.fields['status'].choices] == ['pending', 'paid', 'cancelled']

    delivered = make_order(user, [(product, 1)], status=Order.Status.DELIVERED)
    form = admin_web_client.get(change_url(delivered)).context['adminform'].form
    assert [value for value, _ in form.fields['status'].choices] == ['delivered']


def test_admin_status_change_goes_through_service(admin_web_client, user, product, make_order):
    order = make_order(user, [(product, 3)], status=Order.Status.PAID)
    response = admin_web_client.post(change_url(order), order_form_data(order, 'cancelled'))
    assert response.status_code == 302
    order.refresh_from_db()
    product.refresh_from_db()
    assert order.status == Order.Status.CANCELLED
    assert product.stock == 10


def test_admin_rejects_invalid_transition(admin_web_client, user, product, make_order):
    order = make_order(user, [(product, 1)])
    response = admin_web_client.post(change_url(order), order_form_data(order, 'delivered'))
    assert response.status_code == 200
    assert 'status' in response.context['adminform'].form.errors
    order.refresh_from_db()
    assert order.status == Order.Status.PENDING


def test_admin_can_edit_address_without_status_change(admin_web_client, user, product, make_order):
    order = make_order(user, [(product, 1)])
    data = {**order_form_data(order, 'pending'), 'shipping_address': 'Новый адрес'}
    admin_web_client.post(change_url(order), data)
    order.refresh_from_db()
    assert (order.shipping_address, order.status) == ('Новый адрес', 'pending')


def test_bulk_actions_respect_transitions(admin_web_client, user, product, make_order):
    pending = make_order(user, [(product, 2)])
    paid = make_order(user, [(product, 1)], status=Order.Status.PAID)
    response = admin_web_client.post(
        reverse('admin:orders_order_changelist'),
        {'action': 'mark_shipped', '_selected_action': [pending.pk, paid.pk]},
    )
    messages = [str(m) for m in get_messages(response.wsgi_request)]
    pending.refresh_from_db()
    paid.refresh_from_db()
    assert (pending.status, paid.status) == ('pending', 'shipped')
    assert any('заказов: 1' in m for m in messages)
    assert any(f'№{pending.pk}' in m for m in messages)


def test_bulk_cancel_restores_stock(admin_web_client, user, product, make_order):
    orders = [make_order(user, [(product, 2)]) for _ in range(2)]
    admin_web_client.post(
        reverse('admin:orders_order_changelist'),
        {'action': 'mark_cancelled', '_selected_action': [o.pk for o in orders]},
    )
    product.refresh_from_db()
    assert product.stock == 10


@pytest.mark.parametrize('action', ['mark_paid', 'mark_delivered'])
def test_other_bulk_actions(admin_web_client, user, product, make_order, action):
    order = make_order(
        user,
        [(product, 1)],
        status=Order.Status.SHIPPED if action == 'mark_delivered' else 'pending',
    )
    admin_web_client.post(
        reverse('admin:orders_order_changelist'), {'action': action, '_selected_action': [order.pk]}
    )
    order.refresh_from_db()
    assert order.status == {'mark_paid': 'paid', 'mark_delivered': 'delivered'}[action]


def test_product_activation_actions(admin_web_client, make_product):
    product = make_product()
    url = reverse('admin:products_product_changelist')
    admin_web_client.post(url, {'action': 'deactivate', '_selected_action': [product.pk]})
    product.refresh_from_db()
    assert not product.is_active
    admin_web_client.post(url, {'action': 'activate', '_selected_action': [product.pk]})
    product.refresh_from_db()
    assert product.is_active


def test_analytics_page_numbers(admin_web_client, user, make_product, make_order):
    hops = make_product(name='Хмель X', price=10)
    make_order(user, [(hops, 2)], status=Order.Status.DELIVERED)
    make_order(user, [(hops, 1)], status=Order.Status.PAID)
    make_order(user, [(hops, 5)], status=Order.Status.CANCELLED)
    context = admin_web_client.get(reverse('admin:orders_order_analytics')).context
    summary = context['summary']
    assert (summary.revenue, summary.sold_orders, summary.total_orders) == (30, 2, 3)
    assert summary.average_order_value == 15
    assert [(p.name, p.popularity) for p in context['top_products']] == [('Хмель X', 3)]
    assert ('cancelled', 'Отменён', 1) in context['by_status']
    assert context['customers']['repeat_buyers'] == 1
