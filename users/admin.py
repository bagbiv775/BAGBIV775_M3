from django.contrib import admin

from users.models import Address


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ('label', 'user', 'full_name', 'city', 'phone')
    list_filter = ('city',)
    search_fields = ('label', 'full_name', 'city', 'address', 'user__username')
    list_select_related = ('user',)
    autocomplete_fields = ('user',)
