import json
from pathlib import Path
from typing import Any

from django.contrib.auth.models import User
from django.core.files import File
from django.core.management.base import BaseCommand
from django.db import transaction

from orders.models import Order
from orders.services import OrderLine, change_order_status, create_order
from products.models import Category, Product
from reviews.models import Review

DATA_DIR = Path(__file__).resolve().parents[2] / 'demo_data'

DEMO_REVIEWS = [
    ('citra-hops', 5, 'Невероятный аромат грейпфрута и маракуйи — сварил NEIPA, все в восторге.'),
    ('citra-hops', 4, 'Отличный хмель, но в этот раз гранулы были немного раскрошены.'),
    ('safale-us05-yeast', 5, 'Надёжные дрожжи: стартуют быстро, бродят чисто.'),
    ('maris-otter-malt', 5, 'Тот самый бисквитный вкус, ради которого его и берут.'),
]


class Command(BaseCommand):
    help = 'Fill the database with demo categories, products, users, orders and reviews.'

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            '--no-users',
            action='store_true',
            help='Create only the catalog, without demo accounts, orders and reviews.',
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        catalog = json.loads((DATA_DIR / 'catalog.json').read_text(encoding='utf-8'))
        categories = {
            item['slug']: Category.objects.get_or_create(
                slug=item['slug'], defaults={'name': item['name']}
            )[0]
            for item in catalog['categories']
        }

        created = 0
        for item in catalog['products']:
            product, is_new = Product.objects.get_or_create(
                slug=item['slug'],
                defaults={
                    'name': item['name'],
                    'description': item['description'],
                    'price': item['price'],
                    'stock': item['stock'],
                    'category': categories[item['category']],
                },
            )
            if is_new:
                created += 1
            image_name = product.image.name
            if not image_name or not product.image.storage.exists(image_name):
                with (DATA_DIR / 'images' / item['image']).open('rb') as image:
                    product.image.save(item['image'], File(image), save=True)
        self.stdout.write(f'Каталог: {len(categories)} категорий, новых товаров: {created}.')

        if not options['no_users']:
            self._create_users_orders_and_reviews()

    def _create_users_orders_and_reviews(self) -> None:
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser('admin', 'admin@hop-and-barley.local', 'admin12345')
            self.stdout.write('Создан администратор admin / admin12345.')

        customer, is_new = User.objects.get_or_create(
            username='demo',
            defaults={'email': 'demo@hop-and-barley.local', 'first_name': 'Демо'},
        )
        if is_new:
            customer.set_password('demo12345')
            customer.save()
            self.stdout.write('Создан покупатель demo / demo12345.')

        if not Order.objects.filter(user=customer).exists():
            products = Product.objects.in_bulk(
                ['citra-hops', 'cascade-hops', 'pilsner-malt'], field_name='slug'
            )
            delivered = create_order(
                user=customer,
                lines=[
                    OrderLine(products['citra-hops'].pk, 2),
                    OrderLine(products['pilsner-malt'].pk, 5),
                ],
                shipping_address='Алматы, ул. Абая, 1',
                payment_method=Order.PaymentMethod.CARD,
                contact_name='Демо Покупатель',
                contact_phone='+7 700 000 00 00',
            )
            for status in (Order.Status.PAID, Order.Status.SHIPPED, Order.Status.DELIVERED):
                change_order_status(delivered, status)
            create_order(
                user=customer,
                lines=[OrderLine(products['cascade-hops'].pk, 1)],
                shipping_address='Алматы, ул. Абая, 1',
                payment_method=Order.PaymentMethod.CASH,
                contact_name='Демо Покупатель',
                contact_phone='+7 700 000 00 00',
            )
            self.stdout.write('Для demo созданы заказы: один доставлен, один ожидает оплаты.')

        # Demo reviews follow the same rule as real ones: the author has a
        # delivered order with the product.
        for index, (slug, rating, comment) in enumerate(DEMO_REVIEWS, start=1):
            author, _ = User.objects.get_or_create(username=f'brewer{index}')
            product = Product.objects.get(slug=slug)
            if Review.objects.filter(user=author, product=product).exists():
                continue
            order = create_order(
                user=author,
                lines=[OrderLine(product.pk, 1)],
                shipping_address='Астана, пр. Республики, 10',
                payment_method=Order.PaymentMethod.WALLET,
            )
            for status in (Order.Status.PAID, Order.Status.SHIPPED, Order.Status.DELIVERED):
                change_order_status(order, status)
            Review.objects.create(user=author, product=product, rating=rating, comment=comment)
