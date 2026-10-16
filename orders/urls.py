from django.urls import path

from orders import views

app_name = 'orders'

urlpatterns = [
    path('cart/', views.CartDetailView.as_view(), name='cart'),
    path('cart/add/<int:product_id>/', views.CartAddView.as_view(), name='cart_add'),
    path('cart/update/<int:product_id>/', views.CartUpdateView.as_view(), name='cart_update'),
    path('cart/remove/<int:product_id>/', views.CartRemoveView.as_view(), name='cart_remove'),
    path('checkout/', views.CheckoutView.as_view(), name='checkout'),
    path('checkout/done/<int:pk>/', views.CheckoutDoneView.as_view(), name='checkout_done'),
    path('account/orders/<int:pk>/', views.OrderDetailView.as_view(), name='detail'),
    path('account/orders/<int:pk>/cancel/', views.OrderCancelView.as_view(), name='cancel'),
]
