import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

from orders.models import Order
from reviews.forms import ReviewForm
from reviews.models import Review

pytestmark = pytest.mark.django_db


def detail_url(product):
    return reverse('products:detail', kwargs={'slug': product.slug})


def review_url(product):
    return reverse('reviews:create', kwargs={'slug': product.slug})


def messages_of(response):
    return [str(message) for message in get_messages(response.wsgi_request)]


def test_product_page_shows_details_and_no_rating(client, product):
    response = client.get(detail_url(product))
    assert response.status_code == 200
    assert 'Хмель Citra' in response.text
    assert '$5.99' in response.text
    assert 'Нет оценок' in response.text
    assert 'Добавить в корзину' in response.text


def test_product_page_shows_average_rating(client, product, make_user):
    for rating in (5, 4):
        Review.objects.create(user=make_user(), product=product, rating=rating, comment='ok')
    response = client.get(detail_url(product))
    assert response.context['product'].avg_rating == pytest.approx(4.5)
    assert '4,5' in response.text
    assert 'Нет оценок' not in response.text


def test_inactive_or_missing_product_is_404(client, make_product):
    hidden = make_product(is_active=False)
    assert client.get(detail_url(hidden)).status_code == 404
    assert client.get('/product/missing/').status_code == 404


def test_review_form_visibility(client, auth_client, user, product, make_order):
    assert 'review_form' not in client.get(detail_url(product)).context
    response = auth_client.get(detail_url(product))
    assert 'review_form' not in response.context
    assert 'доставленного заказа' in response.context['review_denial_reason']

    make_order(user, [(product, 1)], status=Order.Status.DELIVERED)
    assert 'review_form' in auth_client.get(detail_url(product)).context


def test_anonymous_cannot_post_review(client, product):
    response = client.post(review_url(product), {'rating': 5, 'comment': 'x'})
    assert response.status_code == 302
    assert reverse('users:login') in response.url
    assert not Review.objects.exists()


@pytest.mark.parametrize('status', [Order.Status.PENDING, Order.Status.PAID, Order.Status.SHIPPED])
def test_review_requires_delivered_purchase(auth_client, user, product, make_order, status):
    make_order(user, [(product, 1)], status=status)
    response = auth_client.post(review_url(product), {'rating': 5, 'comment': 'x'})
    assert response.status_code == 302
    assert not Review.objects.exists()
    assert any('доставленного заказа' in m for m in messages_of(response))


def test_buyer_can_review_once(auth_client, user, product, make_order):
    make_order(user, [(product, 1)], status=Order.Status.DELIVERED)

    response = auth_client.post(review_url(product), {'rating': 4, 'comment': 'Свежий хмель'})
    assert response.url.endswith('#reviews')
    assert messages_of(response) == ['Спасибо! Ваш отзыв опубликован.']
    review = Review.objects.get()
    assert (review.user, review.product, review.rating) == (user, product, 4)

    response = auth_client.post(review_url(product), {'rating': 1, 'comment': 'ещё раз'})
    assert Review.objects.count() == 1
    assert any('уже оставили' in m for m in messages_of(response))


@pytest.mark.parametrize('rating', ['0', '6', 'abc', ''])
def test_invalid_rating_is_rejected(auth_client, user, product, make_order, rating):
    make_order(user, [(product, 1)], status=Order.Status.DELIVERED)
    response = auth_client.post(review_url(product), {'rating': rating, 'comment': 'x'})
    assert not Review.objects.exists()
    assert any('Отзыв не принят' in m for m in messages_of(response))


def test_review_form_and_model_validate_rating(user, product, make_order):
    make_order(user, [(product, 1)], status=Order.Status.DELIVERED)
    form = ReviewForm(data={'rating': 7, 'comment': 'x'}, user=user, product=product)
    assert not form.is_valid()
    assert 'rating' in form.errors

    model_review = Review(user=user, product=product, rating=9, comment='x')
    with pytest.raises(Exception, match='5'):
        model_review.full_clean()


def test_review_list_is_public(client, product, make_user):
    Review.objects.create(user=make_user('reviewer'), product=product, rating=5, comment='Супер')
    response = client.get(detail_url(product))
    assert 'Супер' in response.text
    assert 'reviewer' in response.text


def test_review_for_inactive_product_is_404(auth_client, make_product):
    hidden = make_product(is_active=False)
    assert auth_client.post(review_url(hidden), {'rating': 5, 'comment': 'x'}).status_code == 404
