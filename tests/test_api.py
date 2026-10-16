from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from orders.models import Order
from reviews.models import Review

pytestmark = pytest.mark.django_db

PRODUCTS = '/api/products/'
ORDERS = '/api/orders/'


def order_payload(*items, **extra):
    return {
        'items': [{'product_id': product.pk, 'quantity': quantity} for product, quantity in items],
        'shipping_address': 'Алматы, ул. Абая, 1',
        'payment_method': 'card',
        **extra,
    }


class TestProducts:
    def test_list_is_public_paginated_and_hides_inactive(self, api_client, make_product):
        for _ in range(11):
            make_product()
        make_product(is_active=False)
        response = api_client.get(PRODUCTS)
        assert response.status_code == 200
        assert response.data['count'] == 11
        assert len(response.data['results']) == 10
        assert response.data['next'].endswith('?page=2')

    def test_filters_search_and_ordering(self, api_client, make_product, make_category):
        malts = make_category(slug='malts')
        make_product(name='Citra', price=Decimal('6'))
        make_product(name='Mosaic', price=Decimal('9'), description='тропический')
        make_product(name='Pilsner', price=Decimal('2'), category=malts, stock=0)

        def slugs(**params):
            return [p['name'] for p in api_client.get(PRODUCTS, params).data['results']]

        assert slugs(category='malts') == ['Pilsner']
        assert slugs(min_price=5, ordering='price') == ['Citra', 'Mosaic']
        assert slugs(max_price=5) == ['Pilsner']
        assert slugs(search='тропич') == ['Mosaic']
        assert slugs(ordering='-price') == ['Mosaic', 'Citra', 'Pilsner']
        assert slugs(in_stock='false') == ['Pilsner']
        assert 'Pilsner' not in slugs(in_stock='true')

    def test_ordering_by_popularity(self, api_client, user, make_product, make_order):
        quiet, hit = make_product(name='quiet'), make_product(name='hit')
        make_order(user, [(hit, 2)], status=Order.Status.PAID)
        data = api_client.get(PRODUCTS, {'ordering': '-popularity'}).data['results']
        assert [(p['name'], p['popularity']) for p in data] == [('hit', 2), ('quiet', 0)]
        assert quiet.pk

    def test_detail_with_average_rating(self, api_client, product, make_user):
        response = api_client.get(f'{PRODUCTS}{product.pk}/')
        assert response.data['avg_rating'] is None
        assert response.data['category'] == {
            'id': product.category.pk,
            'name': 'Хмель',
            'slug': 'hops',
        }
        assert response.data['price'] == '5.99'

        for rating in (5, 4, 4):
            Review.objects.create(user=make_user(), product=product, rating=rating, comment='x')
        assert api_client.get(f'{PRODUCTS}{product.pk}/').data['avg_rating'] == 4.33

    def test_products_are_read_only(self, jwt_client, product):
        assert jwt_client.post(PRODUCTS, {'name': 'x'}).status_code == 405
        assert jwt_client.delete(f'{PRODUCTS}{product.pk}/').status_code == 405

    def test_inactive_product_detail_is_404(self, api_client, make_product):
        assert api_client.get(f'{PRODUCTS}{make_product(is_active=False).pk}/').status_code == 404


class TestJWT:
    def test_obtain_refresh_and_use_tokens(self, api_client, user):
        tokens = api_client.post(
            '/api/token/', {'username': 'buyer', 'password': 'Pass12345!'}, format='json'
        ).data
        assert {'access', 'refresh'} <= tokens.keys()

        refreshed = api_client.post(
            '/api/token/refresh/', {'refresh': tokens['refresh']}, format='json'
        )
        assert refreshed.status_code == 200 and 'access' in refreshed.data

        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {refreshed.data["access"]}')
        assert api_client.get(ORDERS).status_code == 200

    def test_bad_credentials_and_tokens(self, api_client, user):
        assert (
            api_client.post('/api/token/', {'username': 'buyer', 'password': 'no'}).status_code
            == 401
        )
        api_client.credentials(HTTP_AUTHORIZATION='Bearer broken')
        assert api_client.get(ORDERS).status_code == 401

    def test_session_auth_is_not_accepted_by_api(self, auth_client):
        assert auth_client.get(ORDERS).status_code == 401


class TestOrders:
    def test_orders_require_jwt(self, api_client):
        assert api_client.get(ORDERS).status_code == 401
        assert api_client.post(ORDERS, {}, format='json').status_code == 401

    def test_create_order_ignores_client_controlled_fields(
        self, jwt_client, user, other_user, make_product
    ):
        hops = make_product(price=Decimal('5.99'), stock=5)
        malt = make_product(price=Decimal('2.50'), stock=5)
        payload = order_payload(
            (hops, 2),
            (malt, 1),
            user=other_user.pk,
            status='delivered',
            total_price='0.01',
            contact_name='Иван',
        )
        payload['items'][0]['price'] = '0.01'

        response = jwt_client.post(ORDERS, payload, format='json')

        assert response.status_code == 201, response.data
        order = Order.objects.get(pk=response.data['id'])
        assert order.user == user
        assert order.status == 'pending'
        assert order.total_price == Decimal('14.48')
        assert response.data['total_price'] == '14.48'
        assert [i['price'] for i in response.data['items']] == ['5.99', '2.50']
        assert response.data['contact_name'] == 'Иван'
        hops.refresh_from_db()
        assert hops.stock == 3

    @pytest.mark.parametrize(
        'mutate',
        [
            lambda p: p.update(items=[]),
            lambda p: p['items'][0].update(quantity=0),
            lambda p: p['items'][0].update(product_id='abc'),
            lambda p: p.update(payment_method='crypto'),
            lambda p: p.pop('shipping_address'),
        ],
    )
    def test_invalid_payloads(self, jwt_client, product, mutate):
        payload = order_payload((product, 1))
        mutate(payload)
        assert jwt_client.post(ORDERS, payload, format='json').status_code == 400
        assert not Order.objects.exists()

    def test_business_errors_are_400_and_atomic(self, jwt_client, make_product):
        ok, scarce, hidden = (
            make_product(stock=5),
            make_product(stock=1),
            make_product(is_active=False),
        )
        response = jwt_client.post(ORDERS, order_payload((ok, 1), (scarce, 3)), format='json')
        assert response.status_code == 400
        assert 'Недостаточно товара' in response.data['items'][0]
        response = jwt_client.post(ORDERS, order_payload((hidden, 1)), format='json')
        assert 'снят с продажи' in response.data['items'][0]
        ok.refresh_from_db()
        assert ok.stock == 5
        assert not Order.objects.exists()

    def test_list_and_detail_only_own(self, jwt_client, user, other_user, product, make_order):
        mine = make_order(user, [(product, 1)])
        foreign = make_order(other_user, [(product, 1)])
        listing = jwt_client.get(ORDERS).data
        assert [o['id'] for o in listing['results']] == [mine.pk]
        assert jwt_client.get(f'{ORDERS}{mine.pk}/').data['items'][0]['product_id'] == product.pk
        assert jwt_client.get(f'{ORDERS}{foreign.pk}/').status_code == 404

    def test_update_and_delete_are_not_allowed(self, jwt_client, user, product, make_order):
        order = make_order(user, [(product, 1)])
        url = f'{ORDERS}{order.pk}/'
        assert jwt_client.put(url, {}, format='json').status_code == 405
        assert jwt_client.patch(url, {'status': 'paid'}, format='json').status_code == 405
        assert jwt_client.delete(url).status_code == 405
        order.refresh_from_db()
        assert order.status == 'pending'

    def test_cancel(self, jwt_client, user, other_user, product, make_order):
        order = make_order(user, [(product, 3)])
        response = jwt_client.post(f'{ORDERS}{order.pk}/cancel/')
        assert response.status_code == 200
        assert response.data['status'] == 'cancelled'
        product.refresh_from_db()
        assert product.stock == 10

        again = jwt_client.post(f'{ORDERS}{order.pk}/cancel/')
        assert again.status_code == 400
        product.refresh_from_db()
        assert product.stock == 10

        paid = make_order(user, [(product, 1)], status=Order.Status.PAID)
        assert jwt_client.post(f'{ORDERS}{paid.pk}/cancel/').status_code == 400

        foreign = make_order(other_user, [(product, 1)])
        assert jwt_client.post(f'{ORDERS}{foreign.pk}/cancel/').status_code == 404


class TestReviewsApi:
    def url(self, product):
        return f'{PRODUCTS}{product.pk}/reviews/'

    def test_public_list(self, api_client, product, make_user):
        Review.objects.create(user=make_user('alice'), product=product, rating=5, comment='Супер')
        response = api_client.get(self.url(product))
        assert response.status_code == 200
        assert response.data[0]['user'] == 'alice'
        assert response.data[0]['rating'] == 5

    def test_post_requires_jwt(self, api_client, product):
        assert api_client.post(self.url(product), {'rating': 5, 'comment': 'x'}).status_code == 401

    def test_post_requires_delivered_purchase_and_is_unique(
        self, jwt_client, user, product, make_order
    ):
        denied = jwt_client.post(self.url(product), {'rating': 5, 'comment': 'x'}, format='json')
        assert denied.status_code == 400
        assert 'доставленного заказа' in str(denied.data)

        make_order(user, [(product, 1)], status=Order.Status.DELIVERED)
        created = jwt_client.post(
            self.url(product), {'rating': 5, 'comment': 'Отлично'}, format='json'
        )
        assert created.status_code == 201
        assert created.data['user'] == 'buyer'

        duplicate = jwt_client.post(self.url(product), {'rating': 4, 'comment': 'x'}, format='json')
        assert duplicate.status_code == 400
        assert Review.objects.count() == 1

    @pytest.mark.parametrize('rating', [0, 6, 'five'])
    def test_rating_validated_by_serializer(self, jwt_client, user, product, make_order, rating):
        make_order(user, [(product, 1)], status=Order.Status.DELIVERED)
        response = jwt_client.post(
            self.url(product), {'rating': rating, 'comment': 'x'}, format='json'
        )
        assert response.status_code == 400
        assert 'rating' in response.data


class TestRegistrationApi:
    def test_register_returns_tokens(self, api_client, make_jwt_client):
        response = api_client.post(
            '/api/register/',
            {'username': 'apiuser', 'email': 'API@example.com', 'password': 'Str0ng-pass-42'},
            format='json',
        )
        assert response.status_code == 201
        assert {'access', 'refresh'} <= response.data.keys()
        assert 'password' not in response.data
        user = User.objects.get(username='apiuser')
        assert user.email == 'api@example.com' and user.check_password('Str0ng-pass-42')

        jwt = make_jwt_client(user)
        assert jwt.get(ORDERS).status_code == 200

    def test_register_validation(self, api_client, user):
        response = api_client.post(
            '/api/register/',
            {'username': 'buyer', 'email': user.email, 'password': '123'},
            format='json',
        )
        assert response.status_code == 400
        assert {'username', 'email'} <= response.data.keys()
        weak = api_client.post(
            '/api/register/',
            {'username': 'new', 'email': 'n@e.com', 'password': '123'},
            format='json',
        )
        assert weak.status_code == 400


def test_openapi_schema_and_docs(api_client):
    schema = api_client.get('/api/schema/')
    assert schema.status_code == 200
    body = schema.content.decode()
    for path in ('/api/products/', '/api/orders/{id}/cancel/', '/api/token/refresh/', 'jwtAuth'):
        assert path in body
    assert api_client.get('/api/docs/').status_code == 200
    assert api_client.get('/api/redoc/').status_code == 200
