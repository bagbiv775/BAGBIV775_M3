from django.urls import path

from reviews import views

app_name = 'reviews'

urlpatterns = [
    path('product/<slug:slug>/reviews/', views.ReviewCreateView.as_view(), name='create'),
]
