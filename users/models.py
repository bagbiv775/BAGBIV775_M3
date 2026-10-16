from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class Address(TimeStampedModel):
    """A shipping address saved by a customer for quick reuse at checkout."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='addresses',
        verbose_name='пользователь',
    )
    label = models.CharField('название', max_length=50, help_text='Например, «Дом» или «Работа».')
    full_name = models.CharField('получатель', max_length=150)
    phone = models.CharField('телефон', max_length=30)
    city = models.CharField('город', max_length=100)
    address = models.TextField('адрес')

    class Meta:
        verbose_name = 'адрес доставки'
        verbose_name_plural = 'адреса доставки'
        ordering = ['label']

    def __str__(self) -> str:
        return f'{self.label}: {self.city}, {self.address}'
