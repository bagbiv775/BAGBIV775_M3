from django.urls import path

from users import views

app_name = 'users'

urlpatterns = [
    path('', views.AccountView.as_view(), name='account'),
    path('register/', views.RegisterView.as_view(), name='register'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('password/', views.PasswordChangeView.as_view(), name='password_change'),
    path('addresses/', views.AddressListView.as_view(), name='addresses'),
    path('addresses/add/', views.AddressCreateView.as_view(), name='address_add'),
    path('addresses/<int:pk>/edit/', views.AddressUpdateView.as_view(), name='address_edit'),
    path('addresses/<int:pk>/delete/', views.AddressDeleteView.as_view(), name='address_delete'),
]
