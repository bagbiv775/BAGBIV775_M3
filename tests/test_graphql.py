import pytest

from orders.models import Order

pytestmark = pytest.mark.django_db

QUERY = """
{
  salesSummary { revenue soldOrders averageOrderValue totalOrders }
  ordersByStatus { status count }
  revenueTrend(days: 7) { day revenue orders }
  topProducts(limit: 2) { name sold stock category }
  lowStockProducts(threshold: 5) { name stock }
  customerActivity { registered withOrders buyers repeatBuyers }
  repeatCustomers { username ordersCount totalSpent }
}
"""


@pytest.fixture
def sales(user, make_user, make_product, make_order):
    hops = make_product(name='Hops', price=10, stock=20)
    malt = make_product(name='Malt', price=4, stock=10)
    make_order(user, [(hops, 2)], status=Order.Status.DELIVERED)
    make_order(user, [(malt, 1)], status=Order.Status.PAID)
    make_order(make_user(), [(malt, 3)], status=Order.Status.CANCELLED)
    make_order(make_user(), [(hops, 1)])


def post(client, query=QUERY):
    return client.post('/graphql/', {'query': query}, content_type='application/json').json()


def test_anonymous_and_customers_are_denied(client, user, sales, make_jwt_client):
    assert 'только сотрудникам' in post(client)['errors'][0]['message']
    client.force_login(user)
    assert post(client)['errors']
    assert post(make_jwt_client(user))['errors']


def test_staff_session_gets_analytics(admin_web_client, sales):
    data = post(admin_web_client)['data']
    assert data['salesSummary'] == {
        'revenue': '24.00',
        'soldOrders': 2,
        'averageOrderValue': '12.00',
        'totalOrders': 4,
    }
    assert {'status': 'cancelled', 'count': 1} in data['ordersByStatus']
    assert data['topProducts'][0] == {'name': 'Hops', 'sold': 2, 'stock': 17, 'category': 'Хмель'}
    assert data['revenueTrend'][0]['revenue'] == '24.00'
    assert data['lowStockProducts'] == []
    assert data['customerActivity']['repeatBuyers'] == 1
    assert data['repeatCustomers'] == [
        {'username': 'buyer', 'ordersCount': 2, 'totalSpent': '24.00'}
    ]


def test_staff_jwt_is_accepted(staff_user, sales, make_jwt_client):
    data = (
        make_jwt_client(staff_user)
        .post('/graphql/', {'query': '{ salesSummary { soldOrders } }'}, format='json')
        .json()
    )
    assert data == {'data': {'salesSummary': {'soldOrders': 2}}}


def test_invalid_jwt_falls_back_to_anonymous(client):
    response = client.post(
        '/graphql/',
        {'query': '{ salesSummary { soldOrders } }'},
        content_type='application/json',
        HTTP_AUTHORIZATION='Bearer nonsense',
    ).json()
    assert response['errors']


def test_days_argument_is_validated(admin_web_client):
    result = post(admin_web_client, '{ revenueTrend(days: 0) { day } }')
    assert 'от 1 до 366' in result['errors'][0]['message']


def test_graphiql_page(admin_web_client):
    response = admin_web_client.get('/graphql/', HTTP_ACCEPT='text/html')
    assert response.status_code == 200
