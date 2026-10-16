from __future__ import annotations

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Avg, IntegerField, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.urls import reverse

from core.models import TimeStampedModel


class Category(TimeStampedModel):
    name = models.CharField('название', max_length=100)
    slug = models.SlugField('slug', max_length=100, unique=True)

    class Meta:
        verbose_name = 'категория'
        verbose_name_plural = 'категории'
        ordering = ['name']

    def __str__(self) -> str:
        return self.name


class ProductQuerySet(models.QuerySet['Product']):
    def active(self) -> ProductQuerySet:
        return self.filter(is_active=True)

    def with_rating(self) -> ProductQuerySet:
        """Annotate `avg_rating` (None when the product has no reviews).

        A subquery is used instead of a plain `Avg('reviews__rating')` so that the
        annotation can be combined with `with_popularity()` without the JOINs
        multiplying each other's rows.
        """
        from reviews.models import Review

        rating = (
            Review.objects.filter(product=OuterRef('pk'))
            .values('product')
            .annotate(value=Avg('rating'))
            .values('value')
        )
        return self.annotate(avg_rating=Subquery(rating))

    def with_popularity(self) -> ProductQuerySet:
        """Annotate `popularity`: units sold in paid, shipped and delivered orders."""
        from orders.models import SOLD_STATUSES, OrderItem

        sold = (
            OrderItem.objects.filter(
                product=OuterRef('pk'),
                order__status__in=SOLD_STATUSES,
            )
            .values('product')
            .annotate(total=Sum('quantity'))
            .values('total')
        )
        return self.annotate(
            popularity=Coalesce(Subquery(sold, output_field=IntegerField()), 0),
        )


class Product(TimeStampedModel):
    name = models.CharField('название', max_length=200)
    slug = models.SlugField('slug', max_length=200, unique=True)
    description = models.TextField('описание', blank=True)
    price = models.DecimalField(
        'цена',
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='products',
        verbose_name='категория',
    )
    image = models.ImageField('изображение', upload_to='products/', blank=True)
    is_active = models.BooleanField('в продаже', default=True)
    stock = models.IntegerField('остаток', default=0, validators=[MinValueValidator(0)])

    objects = ProductQuerySet.as_manager()

    class Meta:
        verbose_name = 'товар'
        verbose_name_plural = 'товары'
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(condition=Q(price__gte=0), name='product_price_non_negative'),
            models.CheckConstraint(condition=Q(stock__gte=0), name='product_stock_non_negative'),
        ]
        indexes = [models.Index(fields=['is_active', 'price'])]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        return reverse('products:detail', kwargs={'slug': self.slug})

    @property
    def is_available(self) -> bool:
        return self.is_active and self.stock > 0
