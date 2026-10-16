from django.contrib import admin

from reviews.models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('product', 'user', 'rating', 'short_comment', 'created_at')
    list_filter = ('rating', 'created_at')
    search_fields = ('product__name', 'user__username', 'comment')
    list_select_related = ('product', 'user')
    autocomplete_fields = ('product', 'user')
    readonly_fields = ('created_at',)

    @admin.display(description='комментарий')
    def short_comment(self, obj: Review) -> str:
        return obj.comment if len(obj.comment) <= 60 else f'{obj.comment[:60]}…'
