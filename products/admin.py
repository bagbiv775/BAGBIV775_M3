from django.contrib import admin
from django.db.models import Count, QuerySet
from django.http import HttpRequest
from django.utils.html import format_html

from products.models import Category, Product


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'products_count', 'created_at')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}

    def get_queryset(self, request: HttpRequest) -> QuerySet[Category]:
        return super().get_queryset(request).annotate(products_total=Count('products'))

    @admin.display(description='товаров', ordering='products_total')
    def products_count(self, obj: Category) -> int:
        return obj.products_total  # type: ignore[attr-defined]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'stock', 'is_active', 'created_at')
    list_display_links = ('name',)
    list_editable = ('price', 'stock', 'is_active')
    list_filter = ('is_active', 'category', 'created_at')
    search_fields = ('name', 'slug', 'description')
    list_select_related = ('category',)
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('image_preview', 'created_at', 'updated_at')
    fields = (
        'name',
        'slug',
        'category',
        'description',
        ('price', 'stock'),
        'is_active',
        'image',
        'image_preview',
        ('created_at', 'updated_at'),
    )
    actions = ('activate', 'deactivate')

    @admin.display(description='превью')
    def image_preview(self, obj: Product) -> str:
        if not obj.image:
            return '—'
        return format_html(
            '<img src="{}" style="max-height: 160px; border-radius: 8px;">', obj.image.url
        )

    @admin.action(description='Вернуть в продажу')
    def activate(self, request: HttpRequest, queryset: QuerySet[Product]) -> None:
        updated = queryset.update(is_active=True)
        self.message_user(request, f'Возвращено в продажу: {updated}.')

    @admin.action(description='Снять с продажи')
    def deactivate(self, request: HttpRequest, queryset: QuerySet[Product]) -> None:
        updated = queryset.update(is_active=False)
        self.message_user(request, f'Снято с продажи: {updated}.')
