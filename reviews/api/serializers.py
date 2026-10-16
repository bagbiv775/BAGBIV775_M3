from typing import Any

from django.db import IntegrityError
from rest_framework import serializers

from reviews.models import MAX_RATING, MIN_RATING, Review
from reviews.services import review_denial_reason


class ReviewSerializer(serializers.ModelSerializer):
    user = serializers.CharField(source='user.username', read_only=True)
    rating = serializers.IntegerField(min_value=MIN_RATING, max_value=MAX_RATING)

    class Meta:
        model = Review
        fields = ('id', 'user', 'rating', 'comment', 'created_at')
        read_only_fields = ('id', 'user', 'created_at')

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        reason = review_denial_reason(self.context['request'].user, self.context['product'])
        if reason:
            raise serializers.ValidationError(reason)
        return attrs

    def create(self, validated_data: dict[str, Any]) -> Review:
        try:
            return Review.objects.create(
                user=self.context['request'].user,
                product=self.context['product'],
                **validated_data,
            )
        except IntegrityError as error:
            raise serializers.ValidationError('Вы уже оставили отзыв на этот товар.') from error
