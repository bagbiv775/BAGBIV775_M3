from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

MIN_RATING = 1
MAX_RATING = 5


class Review(models.Model):
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='reviews',
        verbose_name='товар',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reviews',
        verbose_name='автор',
    )
    rating = models.IntegerField(
        'оценка',
        validators=[MinValueValidator(MIN_RATING), MaxValueValidator(MAX_RATING)],
    )
    comment = models.TextField('комментарий')
    created_at = models.DateTimeField('создан', auto_now_add=True)

    class Meta:
        verbose_name = 'отзыв'
        verbose_name_plural = 'отзывы'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'product'], name='unique_review_per_user_product'
            ),
            models.CheckConstraint(
                condition=Q(rating__gte=MIN_RATING) & Q(rating__lte=MAX_RATING),
                name='review_rating_between_1_and_5',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.user} → {self.product}: {self.rating}'
