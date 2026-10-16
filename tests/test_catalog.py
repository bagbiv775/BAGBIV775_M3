from decimal import Decimal

import pytest
from django.urls import reverse

from orders.models import Order

pytestmark = pytest.mark.django_db

CATALOG = reverse('products:catalog')


def names(response):
    return [product.name for product in response.context['products']]


def test_home_and_catalog_render(client, product):
    for url in ('/', CATALOG):
        response = client.get(url)
        assert response.status_code == 200
        assert 'Хмель Citra' in response.text
        assert 'base.html' in [t.name for t in response.templates]


def test_inactive_products_are_hidden(client, make_product):
    make_product(name='Видимый')
    make_product(name='Скрытый', is_active=False)
    assert names(client.get(CATALOG)) == ['Видимый']


def test_search_by_name_and_description(client, make_product):
    make_product(name='Cascade', description='цветочный аромат')
    make_product(name='Pilsner', description='светлый солод')
    assert names(client.get(CATALOG, {'q': 'casc'})) == ['Cascade']
    assert names(client.get(CATALOG, {'q': 'солод'})) == ['Pilsner']


def test_filter_by_category(client, make_product, make_category):
    malts = make_category(name='Солод', slug='malts')
    make_product(name='Хмель')
    make_product(name='Солод', category=malts)
    assert names(client.get(CATALOG, {'category': 'malts'})) == ['Солод']


def test_filter_by_price_range(client, make_product):
    for price in ('1.00', '5.00', '10.00'):
        make_product(name=price, price=Decimal(price))
    response = client.get(CATALOG, {'min_price': '2', 'max_price': '9', 'sort': 'price_asc'})
    assert names(response) == ['5.00']


def test_invalid_price_range_shows_error_and_ignores_filters(client, make_product):
    make_product(price=Decimal('3'))
    response = client.get(CATALOG, {'min_price': '9', 'max_price': '1'})
    assert 'не может быть больше' in response.text
    assert len(response.context['products']) == 1


@pytest.mark.parametrize(
    ('sort', 'expected'),
    [
        ('price_asc', ['cheap', 'middle', 'expensive']),
        ('price_desc', ['expensive', 'middle', 'cheap']),
        ('new', ['expensive', 'middle', 'cheap']),
    ],
)
def test_sorting_by_price_and_novelty(client, make_product, sort, expected):
    make_product(name='cheap', price=Decimal('1'))
    make_product(name='middle', price=Decimal('5'))
    make_product(name='expensive', price=Decimal('9'))
    assert names(client.get(CATALOG, {'sort': sort})) == expected


def test_sorting_by_popularity(client, make_product, make_user, make_order):
    rare, hit, cancelled = (
        make_product(name='rare'),
        make_product(name='hit'),
        make_product(name='cancelled'),
    )
    buyer = make_user()
    make_order(buyer, [(hit, 3)], status=Order.Status.DELIVERED)
    make_order(buyer, [(rare, 1)], status=Order.Status.PAID)
    make_order(buyer, [(cancelled, 5)], status=Order.Status.CANCELLED)
    assert names(client.get(CATALOG, {'sort': 'popular'}))[:2] == ['hit', 'rare']


def test_pagination_keeps_filters(client, make_product):
    for index in range(12):
        make_product(name=f'Хмель {index}')
    first = client.get(CATALOG, {'q': 'Хмель'})
    assert len(first.context['products']) == 9
    assert first.context['page_obj'].paginator.num_pages == 2
    assert '?q=%D0%A5%D0%BC%D0%B5%D0%BB%D1%8C&amp;page=2' in first.text
    second = client.get(CATALOG, {'q': 'Хмель', 'page': 2})
    assert len(second.context['products']) == 3


def test_catalog_query_count_does_not_grow_with_products(
    client, make_product, django_assert_max_num_queries
):
    for _ in range(9):
        make_product()
    with django_assert_max_num_queries(8):
        client.get(CATALOG, {'sort': 'popular'})


def test_out_of_stock_badge(client, make_product):
    make_product(stock=0)
    assert 'Нет в наличии' in client.get(CATALOG).text
