from datetime import datetime, timezone
from decimal import Decimal

from django.http import Http404
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import simulator

# range name -> (window in seconds, number of chart points)
HISTORY_RANGES = {
    '1h': (3600, 60),
    '24h': (86400, 96),
    '7d': (604800, 168),
    '30d': (2592000, 180),
}


def format_price(price):
    """Readable price: cents for BTC, more decimals for DOGE."""
    places = Decimal('0.01') if price >= 1 else Decimal('0.000001')
    return format(price.quantize(places), 'f')


def iso(at):
    return datetime.fromtimestamp(at, tz=timezone.utc).isoformat().replace('+00:00', 'Z')


def price_row(asset, at):
    return {
        'symbol': asset.symbol,
        'name': asset.name,
        'price_usd': format_price(simulator.price_usd(asset.symbol, at)),
        'price_ngn': format_price(simulator.rate(asset.symbol, 'NGN', at)),
        'change_24h_pct': format(simulator.change_24h_pct(asset.symbol, at).quantize(Decimal('0.01')), 'f'),
    }


def get_tradable_asset(symbol):
    asset = simulator.ASSETS.get(symbol.upper())
    if asset is None or asset.is_fiat:
        raise Http404
    return asset


class PublicMarketView(APIView):
    """Market data is public, so a stale token on the request shouldn't cause a 401."""

    permission_classes = [AllowAny]
    authentication_classes = []


class PriceListView(PublicMarketView):
    def get(self, request):
        at = simulator.current_time()
        return Response({
            'as_of': iso(at),
            'tick_seconds': simulator.TICK_SECONDS,
            'prices': [
                price_row(asset, at) for asset in simulator.ASSETS.values() if not asset.is_fiat
            ],
        })


class PriceDetailView(PublicMarketView):
    def get(self, request, symbol):
        asset = get_tradable_asset(symbol)
        at = simulator.current_time()
        return Response({'as_of': iso(at), **price_row(asset, at)})


class PriceHistoryView(PublicMarketView):
    def get(self, request, symbol):
        asset = get_tradable_asset(symbol)
        range_name = request.query_params.get('range', '24h')
        if range_name not in HISTORY_RANGES:
            return Response(
                {'range': f"Choose one of: {', '.join(HISTORY_RANGES)}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        window, points = HISTORY_RANGES[range_name]
        samples = simulator.history(asset.symbol, window, points)
        prices = [price for _, price in samples]
        return Response({
            'symbol': asset.symbol,
            'range': range_name,
            'high_usd': format_price(max(prices)),
            'low_usd': format_price(min(prices)),
            'points': [{'t': iso(at), 'price_usd': format_price(price)} for at, price in samples],
        })
