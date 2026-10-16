from rest_framework import serializers

from products.models import Category, Product


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ('id', 'name', 'slug')


class ProductSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    avg_rating = serializers.SerializerMethodField(
        help_text='Средняя оценка по отзывам; `null`, если отзывов нет.'
    )
    popularity = serializers.IntegerField(
        read_only=True,
        help_text='Продано единиц в оплаченных, отправленных и доставленных заказах.',
    )
    is_available = serializers.BooleanField(read_only=True)

    class Meta:
        model = Product
        fields = (
            'id',
            'name',
            'slug',
            'description',
            'price',
            'category',
            'image',
            'stock',
            'is_available',
            'avg_rating',
            'popularity',
            'created_at',
            'updated_at',
        )

    def get_avg_rating(self, obj: Product) -> float | None:
        rating = getattr(obj, 'avg_rating', None)
        return None if rating is None else round(float(rating), 2)
