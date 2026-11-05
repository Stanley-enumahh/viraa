from django.urls import path

from .views import PriceDetailView, PriceHistoryView, PriceListView

urlpatterns = [
    path('prices/', PriceListView.as_view(), name='price-list'),
    path('prices/<str:symbol>/', PriceDetailView.as_view(), name='price-detail'),
    path('prices/<str:symbol>/history/', PriceHistoryView.as_view(), name='price-history'),
]
