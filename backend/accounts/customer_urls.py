from django.urls import path

from .views import CustomerDetailView, CustomerListView, CustomerLookupView

urlpatterns = [
    path('', CustomerListView.as_view(), name='customer-list'),
    path('lookup/', CustomerLookupView.as_view(), name='customer-lookup'),
    path('<int:pk>/', CustomerDetailView.as_view(), name='customer-detail'),
]
