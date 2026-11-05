import math
from decimal import Decimal
from unittest import mock

from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from . import simulator

# A fixed moment, aligned to a tick.
NOW = 1_800_000_000


class SimulatorTests(SimpleTestCase):
    def test_same_time_gives_same_price(self):
        self.assertEqual(simulator.price_usd('BTC', NOW), simulator.price_usd('BTC', NOW))

    def test_price_is_stable_within_a_tick_and_moves_between_ticks(self):
        self.assertEqual(simulator.price_usd('BTC', NOW), simulator.price_usd('BTC', NOW + simulator.TICK_SECONDS - 1))
        self.assertNotEqual(simulator.price_usd('BTC', NOW), simulator.price_usd('BTC', NOW + simulator.TICK_SECONDS))

    def test_coins_move_independently(self):
        self.assertNotEqual(simulator._wave('ETH', NOW), simulator._wave('SOL', NOW))

    def test_usdt_stays_pegged(self):
        for offset in range(0, 86400, 3600):
            self.assertEqual(simulator.price_usd('USDT', NOW + offset), Decimal(1))

    def test_prices_stay_positive_and_in_a_believable_range(self):
        total_weight = sum(weight for _, weight in simulator.OCTAVES)
        for asset in simulator.ASSETS.values():
            limit = math.exp(asset.volatility * total_weight)
            for offset in range(0, 30 * 86400, 86400 // 4):
                price = float(simulator.price_usd(asset.symbol, NOW + offset))
                self.assertGreater(price, 0)
                self.assertLessEqual(price, asset.base_usd * limit * 1.001)
                self.assertGreaterEqual(price, asset.base_usd / limit * 0.999)

    def test_rate_converts_between_assets(self):
        self.assertAlmostEqual(
            float(simulator.rate('BTC', 'USDT', NOW)), float(simulator.price_usd('BTC', NOW)), places=6,
        )
        round_trip = simulator.rate('USDT', 'NGN', NOW) * simulator.rate('NGN', 'USDT', NOW)
        self.assertAlmostEqual(float(round_trip), 1.0, places=6)

    def test_naira_rate_is_near_its_base(self):
        self.assertTrue(1400 < simulator.rate('USDT', 'NGN', NOW) < 1700)

    def test_history_is_ordered_and_ends_at_the_live_price(self):
        at = NOW + 17
        samples = simulator.history('BTC', 3600, 60, at=at)
        times = [t for t, _ in samples]
        self.assertEqual(times, sorted(times))
        self.assertEqual(samples[-1], (at, simulator.price_usd('BTC', at)))

    def test_history_past_does_not_shift_between_polls(self):
        first = simulator.history('BTC', 3600, 60, at=NOW + 7)
        second = simulator.history('BTC', 3600, 60, at=NOW + 12)
        self.assertEqual(first[:-1], second[:-1])


@mock.patch('market.simulator.time.time', return_value=NOW)
class MarketApiTests(APITestCase):
    def test_price_list_is_public_and_hides_naira(self, _time):
        response = self.client.get(reverse('price-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        symbols = [row['symbol'] for row in response.data['prices']]
        self.assertIn('BTC', symbols)
        self.assertNotIn('NGN', symbols)
        self.assertEqual(response.data['tick_seconds'], simulator.TICK_SECONDS)

    def test_stale_token_does_not_break_public_prices(self, _time):
        self.client.credentials(HTTP_AUTHORIZATION='Bearer not-a-real-token')
        response = self.client.get(reverse('price-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_detail_is_case_insensitive(self, _time):
        response = self.client.get(reverse('price-detail', args=['sol']))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['symbol'], 'SOL')
        self.assertEqual(response.data['name'], 'Solana')

    def test_small_prices_keep_their_decimals(self, _time):
        response = self.client.get(reverse('price-detail', args=['DOGE']))
        self.assertGreater(Decimal(response.data['price_usd']), 0)
        self.assertEqual(len(response.data['price_usd'].split('.')[1]), 6)

    def test_unknown_and_fiat_symbols_are_404(self, _time):
        for symbol in ['NOPE', 'NGN']:
            response = self.client.get(reverse('price-detail', args=[symbol]))
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_history_defaults_to_24h(self, _time):
        response = self.client.get(reverse('price-history', args=['BTC']))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['range'], '24h')
        self.assertGreaterEqual(len(response.data['points']), 96)
        prices = [Decimal(point['price_usd']) for point in response.data['points']]
        self.assertEqual(Decimal(response.data['high_usd']), max(prices))
        self.assertEqual(Decimal(response.data['low_usd']), min(prices))

    def test_invalid_history_range_is_400(self, _time):
        response = self.client.get(reverse('price-history', args=['BTC']), {'range': '5y'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
