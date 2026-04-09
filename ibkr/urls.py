from django.urls import path
from . import views

urlpatterns = [
    path('', views.ibkr_status_page, name='ibkr_status_page'),
    path('status/', views.ibkr_status, name='ibkr_status'),
    path('connect/', views.ibkr_connect, name='ibkr_connect'),
    path('settings/', views.ibkr_settings, name='ibkr_settings'),
    path('chain/', views.ibkr_chain, name='ibkr_chain'),
    path('greeks/', views.ibkr_greeks, name='ibkr_greeks'),
]
