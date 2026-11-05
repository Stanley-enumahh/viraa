"""
Simulated market prices. All numbers here are fake.

A price is a pure function of (asset, time): layered noise around a base price.
Nothing is stored and no background worker runs, so prices survive restarts,
every client sees the same number, and any point in history can be computed.
"""

import math
import time
from dataclasses import dataclass
from decimal import Decimal
from hashlib import blake2b

TICK_SECONDS = 5

# (period in seconds, weight): slow market trends down to tick-by-tick jitter.
OCTAVES = [
    (259200, 1.0),
    (14400, 0.35),
    (900, 0.15),
    (60, 0.06),
    (TICK_SECONDS, 0.02),
]

RATE_PLACES = Decimal('0.000000000001')


@dataclass(frozen=True)
class Asset:
    symbol: str
    name: str
    base_usd: float
    volatility: float
    is_fiat: bool = False


ASSETS = {
    asset.symbol: asset
    for asset in [
        Asset('BTC', 'Bitcoin', 95000, 0.06),
        Asset('ETH', 'Ethereum', 3200, 0.08),
        Asset('SOL', 'Solana', 180, 0.12),
        Asset('BNB', 'BNB', 650, 0.08),
        Asset('XRP', 'XRP', 2.2, 0.12),
        Asset('ADA', 'Cardano', 0.7, 0.14),
        Asset('DOGE', 'Dogecoin', 0.18, 0.18),
        Asset('USDT', 'Tether', 1, 0),
        Asset('NGN', 'Nigerian Naira', 1 / 1550, 0.01, is_fiat=True),
    ]
}


def current_time():
    return int(time.time())


def _noise(symbol, period, index):
    """Repeatable random value in [-1, 1]."""
    digest = blake2b(f'{symbol}:{period}:{index}'.encode(), digest_size=8).digest()
    return int.from_bytes(digest, 'big') / (2**64 - 1) * 2 - 1


def _wave(symbol, at):
    total = 0.0
    for period, weight in OCTAVES:
        index, remainder = divmod(at, period)
        blend = remainder / period
        blend = blend * blend * (3 - 2 * blend)
        start, end = _noise(symbol, period, index), _noise(symbol, period, index + 1)
        total += weight * (start + (end - start) * blend)
    return total


def price_usd(symbol, at=None):
    """USD price of an asset at a unix time (default: now). Stable within a tick."""
    asset = ASSETS[symbol]
    at = current_time() if at is None else int(at)
    tick = at - at % TICK_SECONDS
    price = asset.base_usd * math.exp(asset.volatility * _wave(symbol, tick))
    return Decimal(str(price)).quantize(RATE_PLACES)


def rate(base, quote, at=None):
    """How much `quote` one unit of `base` buys, e.g. rate('BTC', 'NGN')."""
    at = current_time() if at is None else at
    return price_usd(base, at) / price_usd(quote, at)


def change_24h_pct(symbol, at=None):
    at = current_time() if at is None else at
    then = price_usd(symbol, at - 86400)
    return (price_usd(symbol, at) - then) / then * 100


def history(symbol, window_seconds, points, at=None):
    """Evenly spaced (time, price) samples ending at `at`, oldest first.

    Samples sit on fixed time boundaries so a chart's past doesn't shift between
    polls; the last point is always the live price.
    """
    at = current_time() if at is None else at
    step = window_seconds // points
    last_boundary = at - at % step
    times = [last_boundary - step * i for i in range(points - 1, -1, -1)]
    if times[-1] != at:
        times.append(at)
    return [(t, price_usd(symbol, t)) for t in times]
