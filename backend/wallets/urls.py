from django.urls import path

from .views import (
    NetworkListView,
    PortfolioView,
    SendQuoteView,
    SendView,
    TradeQuoteView,
    TradeView,
    TransactionDetailView,
    TransactionListView,
)

urlpatterns = [
    path('', PortfolioView.as_view(), name='portfolio'),
    path('networks/', NetworkListView.as_view(), name='network-list'),
    path('trades/quote/', TradeQuoteView.as_view(), name='trade-quote'),
    path('trades/', TradeView.as_view(), name='trade'),
    path('send/quote/', SendQuoteView.as_view(), name='send-quote'),
    path('send/', SendView.as_view(), name='send'),
    path('transactions/', TransactionListView.as_view(), name='transaction-list'),
    path('transactions/<uuid:reference>/', TransactionDetailView.as_view(), name='transaction-detail'),
]
