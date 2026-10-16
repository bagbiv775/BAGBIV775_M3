from typing import Any

from django import forms
from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.template.response import TemplateResponse
from django.urls import URLPattern, path

from analytics import selectors
from orders.models import STATUS_TRANSITIONS, Order, OrderItem
from orders.services import OrderError, change_order_status


class OrderItemInline(admin.TabularInline):
    """Order lines are a snapshot of the checkout and cannot be edited."""

    model = OrderItem
    extra = 0
    can_delete = False
    fields = ('product', 'quantity', 'price', 'line_total')
    readonly_fields = fields

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    @admin.display(description='сумма')
    def line_total(self, obj: OrderItem) -> str:
        return f'{obj.line_total:.2f}'


class OrderAdminForm(forms.ModelForm[Order]):
    """Offer only the current status and the statuses it may move to."""

    class Meta:
        model = Order
        fields = ('status', 'contact_name', 'contact_phone', 'shipping_address')

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        status_field = self.fields.get('status')
        if isinstance(status_field, forms.ChoiceField) and self.instance.pk:
            current = self.instance.status
            allowed = {current, *STATUS_TRANSITIONS.get(current, ())}
            status_field.choices = [
                (value, label) for value, label in Order.Status.choices if value in allowed
            ]

    def clean_status(self) -> str:
        new_status: str = self.cleaned_data['status']
        if self.instance.pk:
            current = Order.objects.values_list('status', flat=True).get(pk=self.instance.pk)
            if new_status != current and new_status not in STATUS_TRANSITIONS.get(current, ()):
                raise forms.ValidationError('Недопустимый переход статуса.')
        return new_status


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    form = OrderAdminForm
    inlines = (OrderItemInline,)
    list_display = ('id', 'user', 'status', 'payment_method', 'total_price', 'created_at')
    list_display_links = ('id', 'user')
    list_filter = ('status', 'payment_method', 'created_at')
    search_fields = ('id', 'user__username', 'user__email', 'contact_name', 'shipping_address')
    list_select_related = ('user',)
    date_hierarchy = 'created_at'
    readonly_fields = ('user', 'payment_method', 'total_price', 'created_at', 'updated_at')
    fields = (
        'user',
        'status',
        'payment_method',
        'total_price',
        'contact_name',
        'contact_phone',
        'shipping_address',
        ('created_at', 'updated_at'),
    )
    actions = ('mark_paid', 'mark_shipped', 'mark_delivered', 'mark_cancelled')
    change_list_template = 'admin/orders/order/change_list.html'

    # Orders come only from the storefront and the API, and are never deleted.
    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def save_model(
        self, request: HttpRequest, obj: Order, form: forms.ModelForm[Order], change: bool
    ) -> None:
        """Save editable fields, then change status through the order service.

        The service validates the transition again under a row lock and returns
        stock to the warehouse when the order is cancelled.
        """
        new_status = obj.status
        previous_status = form.initial.get('status', new_status)
        obj.status = previous_status
        super().save_model(request, obj, form, change)
        if new_status != previous_status:
            try:
                change_order_status(obj, new_status)
            except OrderError as error:
                self.message_user(request, ' '.join(error.messages), messages.ERROR)

    def _bulk_change_status(
        self, request: HttpRequest, queryset: QuerySet[Order], new_status: str
    ) -> None:
        changed, rejected = 0, []
        for order in queryset:
            try:
                change_order_status(order, new_status)
            except OrderError:
                rejected.append(f'№{order.pk} ({order.get_status_display()})')
            else:
                changed += 1
        label = Order.Status(new_status).label
        if changed:
            self.message_user(request, f'Статус «{label}» установлен для заказов: {changed}.')
        if rejected:
            self.message_user(
                request,
                f'Пропущены заказы, для которых переход в «{label}» недопустим: '
                + ', '.join(rejected),
                messages.WARNING,
            )

    @admin.action(description='Отметить как оплаченные')
    def mark_paid(self, request: HttpRequest, queryset: QuerySet[Order]) -> None:
        self._bulk_change_status(request, queryset, Order.Status.PAID)

    @admin.action(description='Отметить как отправленные')
    def mark_shipped(self, request: HttpRequest, queryset: QuerySet[Order]) -> None:
        self._bulk_change_status(request, queryset, Order.Status.SHIPPED)

    @admin.action(description='Отметить как доставленные')
    def mark_delivered(self, request: HttpRequest, queryset: QuerySet[Order]) -> None:
        self._bulk_change_status(request, queryset, Order.Status.DELIVERED)

    @admin.action(description='Отменить (вернуть товары на склад)')
    def mark_cancelled(self, request: HttpRequest, queryset: QuerySet[Order]) -> None:
        self._bulk_change_status(request, queryset, Order.Status.CANCELLED)

    def get_urls(self) -> list[URLPattern]:
        custom = [
            path(
                'analytics/',
                self.admin_site.admin_view(self.analytics_view),
                name='orders_order_analytics',
            ),
        ]
        return custom + super().get_urls()

    def analytics_view(self, request: HttpRequest) -> HttpResponse:
        context = {
            **self.admin_site.each_context(request),
            'title': 'Аналитика продаж',
            'opts': self.model._meta,
            'summary': selectors.sales_summary(),
            'by_status': selectors.orders_by_status(),
            'top_products': selectors.top_products(limit=10),
            'low_stock': selectors.low_stock_products(),
            'daily': selectors.daily_revenue(days=30),
            'customers': selectors.customer_activity(),
        }
        return TemplateResponse(request, 'admin/orders/order/analytics.html', context)
