from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .serializers import SendRequestSerializer, TradeRequestSerializer, TransactionSerializer

DEFAULT_TRANSACTION_LIMIT = 50
MAX_TRANSACTION_LIMIT = 200


class WalletApiView(APIView):
    """Turns refused requests into a 400 the frontend can show as-is."""

    def handle_exception(self, exc):
        if isinstance(exc, services.WalletError):
            return Response({'detail': exc.message, 'code': exc.code}, status=status.HTTP_400_BAD_REQUEST)
        return super().handle_exception(exc)


class PortfolioView(APIView):
    def get(self, request):
        return Response(services.portfolio(request.user))


class NetworkListView(APIView):
    def get(self, request):
        return Response(services.available_networks())


class TradeQuoteView(WalletApiView):
    def post(self, request):
        serializer = TradeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quote = services.quote_trade(**serializer.validated_data)
        return Response({
            **quote.as_dict(),
            'has_balance': services.has_balance(request.user, quote.from_asset, quote.from_amount),
        })


class TradeView(WalletApiView):
    def post(self, request):
        serializer = TradeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quote = services.quote_trade(**serializer.validated_data)
        tx = services.execute_trade(request.user, quote)
        return Response(TransactionSerializer(tx).data, status=status.HTTP_201_CREATED)


class SendQuoteView(WalletApiView):
    def post(self, request):
        serializer = SendRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quote = services.quote_send(request.user, **serializer.validated_data)
        return Response({
            **quote.as_dict(),
            'has_balance': services.has_balance(request.user, quote.asset, quote.total),
        })


class SendView(WalletApiView):
    def post(self, request):
        serializer = SendRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quote = services.quote_send(request.user, **serializer.validated_data)
        tx = services.execute_send(request.user, quote)
        return Response(TransactionSerializer(tx).data, status=status.HTTP_201_CREATED)


class TransactionListView(generics.ListAPIView):
    serializer_class = TransactionSerializer

    def get_queryset(self):
        params = self.request.query_params
        transactions = self.request.user.transactions.select_related('counterparty')
        if kind := params.get('kind'):
            transactions = transactions.filter(kind=kind.lower())
        if asset := params.get('asset'):
            asset = asset.upper()
            transactions = transactions.filter(from_asset=asset) | transactions.filter(to_asset=asset)
        try:
            limit = int(params.get('limit', DEFAULT_TRANSACTION_LIMIT))
        except ValueError:
            limit = DEFAULT_TRANSACTION_LIMIT
        return transactions[:max(1, min(limit, MAX_TRANSACTION_LIMIT))]


class TransactionDetailView(generics.RetrieveAPIView):
    serializer_class = TransactionSerializer
    lookup_field = 'reference'

    def get_queryset(self):
        return self.request.user.transactions.select_related('counterparty')
