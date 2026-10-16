from django.urls import path

from analytics.views import graphql_view

urlpatterns = [
    path('', graphql_view, name='graphql'),
]
