from typing import Any

from drf_spectacular.utils import OpenApiExample, extend_schema_serializer
from rest_framework import serializers

from orders.models import Order, OrderItem
from orders.services import OrderError, OrderLine, create_order


class OrderItemSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    line_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = ('product_id', 'product_name', 'quantity', 'price', 'line_total')


class OrderSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = (
            'id',
            'status',
            'status_display',
            'payment_method',
            'total_price',
            'contact_name',
            'contact_phone',
            'shipping_address',
            'items',
            'created_at',
            'updated_at',
        )
        read_only_fields = fields


class OrderItemInputSerializer(serializers.Serializer):
    product_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1)


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            'Новый заказ',
            value={
                'items': [{'product_id': 1, 'quantity': 2}, {'product_id': 3, 'quantity': 1}],
                'shipping_address': 'Алматы, ул. Абая, 1, кв. 5',
                'payment_method': 'card',
                'contact_name': 'Иван Иванов',
                'contact_phone': '+7 700 123 45 67',
            },
            request_only=True,
        )
    ]
)
class OrderCreateSerializer(serializers.Serializer):
    """Input for `POST /api/orders/`.

    The customer, prices, total and status are never taken from the request:
    they come from the JWT and the database.
    """

    items = OrderItemInputSerializer(many=True, allow_empty=False)
    shipping_address = serializers.CharField(max_length=500)
    payment_method = serializers.ChoiceField(choices=Order.PaymentMethod.choices)
    contact_name = serializers.CharField(
        max_length=150, required=False, allow_blank=True, default=''
    )
    contact_phone = serializers.CharField(
        max_length=30, required=False, allow_blank=True, default=''
    )

    def create(self, validated_data: dict[str, Any]) -> Order:
        try:
            return create_order(
                user=self.context['request'].user,
                lines=[
                    OrderLine(item['product_id'], item['quantity'])
                    for item in validated_data['items']
                ],
                shipping_address=validated_data['shipping_address'],
                payment_method=validated_data['payment_method'],
                contact_name=validated_data['contact_name'],
                contact_phone=validated_data['contact_phone'],
            )
        except OrderError as error:
            raise serializers.ValidationError({'items': error.messages}) from error

    def to_representation(self, instance: Order) -> dict[str, Any]:
        return OrderSerializer(instance, context=self.context).data
