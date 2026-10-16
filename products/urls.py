from django.urls import path

from products import views

app_name = 'products'

urlpatterns = [
    path('', views.ProductListView.as_view(), name='home'),
    path('products/', views.ProductListView.as_view(), name='catalog'),
    path('product/<slug:slug>/', views.ProductDetailView.as_view(), name='detail'),
]
