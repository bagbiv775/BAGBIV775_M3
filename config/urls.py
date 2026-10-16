from django.conf import settings
from django.contrib import admin
from django.urls import URLPattern, URLResolver, include, path, re_path
from django.views.static import serve

admin.site.site_header = 'Hop & Barley — администрирование'
admin.site.site_title = 'Hop & Barley'
admin.site.index_title = 'Управление магазином'

urlpatterns: list[URLPattern | URLResolver] = [
    path('admin/', admin.site.urls),
    path('api/', include('config.api_urls')),
    path('graphql/', include('analytics.urls')),
    path('account/', include('users.urls')),
    path('', include('orders.urls')),
    path('', include('reviews.urls')),
    path('', include('products.urls')),
]

if settings.DEBUG or settings.SERVE_MEDIA:
    # Product images are served by Django itself: fine for this training project,
    # a production deployment would put them behind nginx or object storage.
    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    ]
