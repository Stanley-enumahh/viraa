from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from market import simulator

from . import services
from .models import Transaction, Wallet
from .services import WalletError, create_starting_wallets

User = get_user_model()

NOW = 1_800_000_000
ADDRESS = 'bc1qxy2kgdygjrsqtzq2n0yrf2493p83kk'


def make_user(username):
    user = User.objects.create_user(
        username=username, email=f'{username}@example.com', password='x', full_name=username.title(),
    )
    create_starting_wallets(user)
    return user


def balance(user, asset):
    wallet = Wallet.objects.filter(user=user, asset=asset).first()
    return wallet.balance if wallet else Decimal(0)


class TradeQuoteTests(SimpleTestCase):
    def test_fee_comes_out_of_the_amount_paid(self):
        quote = services.quote_trade('buy', 'NGN', 'BTC', Decimal('20000'), at=NOW)
        self.assertEqual(quote.from_amount, Decimal('20000'))
        self.assertEqual(quote.fee_amount, Decimal('100'))
        expected = (Decimal('19900') * simulator.rate('NGN', 'BTC', NOW)).quantize(Decimal('0.00000001'))
        self.assertAlmostEqual(quote.to_amount, expected, delta=Decimal('0.00000001'))

    def test_amount_can_be_given_in_the_coin_being_bought(self):
        quote = services.quote_trade('buy', 'NGN', 'BTC', Decimal('0.01'), amount_asset='BTC', at=NOW)
        self.assertEqual(quote.to_amount, Decimal('0.01'))
        net_value = (quote.from_amount - quote.fee_amount) * simulator.rate('NGN', 'BTC', NOW)
        self.assertAlmostEqual(net_value, Decimal('0.01'), delta=Decimal('0.000001'))

    def test_small_naira_buy_keeps_precision(self):
        # NGN -> BTC is a tiny rate, so rounding it would visibly skew the amount.
        quote = services.quote_trade('buy', 'NGN', 'BTC', Decimal('1000000'), at=NOW)
        exact = Decimal('995000') * simulator.price_usd('NGN', NOW) / simulator.price_usd('BTC', NOW)
        self.assertAlmostEqual(quote.to_amount, exact, delta=Decimal('0.00000002'))

    def test_invalid_pairs_are_refused(self):
        cases = [
            ('buy', 'BTC', 'BTC'),
            ('buy', 'ETH', 'BTC'),
            ('buy', 'USDT', 'NGN'),
            ('sell', 'NGN', 'BTC'),
            ('sell', 'BTC', 'ETH'),
            ('swap', 'NGN', 'BTC'),
            ('steal', 'NGN', 'BTC'),
        ]
        for kind, from_asset, to_asset in cases:
            with self.subTest(kind=kind, from_asset=from_asset, to_asset=to_asset):
                with self.assertRaises(WalletError) as ctx:
                    services.quote_trade(kind, from_asset, to_asset, Decimal(1), at=NOW)
                self.assertEqual(ctx.exception.code, 'invalid_pair')

    def test_unknown_asset_is_refused(self):
        with self.assertRaises(WalletError) as ctx:
            services.quote_trade('buy', 'NGN', 'NOPE', Decimal(1), at=NOW)
        self.assertEqual(ctx.exception.code, 'unknown_asset')

    def test_amount_in_a_third_asset_is_refused(self):
        with self.assertRaises(WalletError) as ctx:
            services.quote_trade('buy', 'NGN', 'BTC', Decimal(1), amount_asset='ETH', at=NOW)
        self.assertEqual(ctx.exception.code, 'invalid_amount')

    def test_dust_is_refused(self):
        with self.assertRaises(WalletError) as ctx:
            services.quote_trade('buy', 'NGN', 'BTC', Decimal('0.01'), at=NOW)
        self.assertEqual(ctx.exception.code, 'amount_too_small')


class ExecuteTradeTests(TestCase):
    def setUp(self):
        self.user = make_user('ada')

    def test_buy_moves_funds_and_records_transaction(self):
        quote = services.quote_trade('buy', 'NGN', 'BTC', Decimal('20000'), at=NOW)
        btc_before = balance(self.user, 'BTC')

        tx = services.execute_trade(self.user, quote)

        self.assertEqual(balance(self.user, 'NGN'), Decimal('480000'))
        self.assertEqual(balance(self.user, 'BTC'), btc_before + quote.to_amount)
        self.assertEqual(tx.kind, 'buy')
        self.assertEqual(self.user.transactions.count(), 1)

    def test_creates_wallet_for_a_coin_the_user_has_never_held(self):
        self.assertFalse(Wallet.objects.filter(user=self.user, asset='BNB').exists())
        quote = services.quote_trade('buy', 'USDT', 'BNB', Decimal('100'), at=NOW)
        services.execute_trade(self.user, quote)
        self.assertEqual(balance(self.user, 'BNB'), quote.to_amount)

    def test_insufficient_funds_changes_nothing(self):
        quote = services.quote_trade('buy', 'NGN', 'BTC', Decimal('500001'), at=NOW)
        btc_before = balance(self.user, 'BTC')

        with self.assertRaises(WalletError) as ctx:
            services.execute_trade(self.user, quote)

        self.assertEqual(ctx.exception.code, 'insufficient_funds')
        self.assertEqual(balance(self.user, 'NGN'), Decimal('500000'))
        self.assertEqual(balance(self.user, 'BTC'), btc_before)
        self.assertFalse(self.user.transactions.exists())

    def test_user_can_spend_their_whole_balance(self):
        quote = services.quote_trade('sell', 'SOL', 'NGN', Decimal('2'), at=NOW)
        services.execute_trade(self.user, quote)
        self.assertEqual(balance(self.user, 'SOL'), Decimal(0))

    def test_failure_after_debit_rolls_everything_back(self):
        quote = services.quote_trade('buy', 'NGN', 'BTC', Decimal('20000'), at=NOW)
        with mock.patch.object(services.Transaction.objects, 'create', side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                services.execute_trade(self.user, quote)
        self.assertEqual(balance(self.user, 'NGN'), Decimal('500000'))


class SendTests(TestCase):
    def setUp(self):
        self.ada, self.bola = make_user('ada'), make_user('bola')

    def test_send_to_a_user_charges_the_network_fee_and_records_both_sides(self):
        quote = services.quote_send(self.ada, 'usdt', Decimal('50'), recipient='@BOLA', network='tron')
        tx = services.execute_send(self.ada, quote)

        self.assertEqual(quote.network, 'TRC20')
        self.assertEqual(quote.fee_amount, Decimal('1'))
        self.assertEqual(balance(self.ada, 'USDT'), Decimal('199'))
        self.assertEqual(balance(self.bola, 'USDT'), Decimal('300'))
        self.assertEqual((tx.kind, tx.network), ('send', 'TRC20'))
        received = self.bola.transactions.get()
        self.assertEqual((received.kind, received.network), ('receive', 'TRC20'))

    def test_each_network_has_its_own_fee(self):
        fees = {
            name: services.quote_send(self.ada, 'USDT', Decimal('5'), recipient='bola', network=name).fee_amount
            for name in ['TRC-20', 'BNB Chain', 'erc20']
        }
        self.assertEqual(fees, {'TRC-20': Decimal('1'), 'BNB Chain': Decimal('0.30'), 'erc20': Decimal('5')})

    def test_usdt_needs_a_network_choice(self):
        with self.assertRaises(WalletError) as ctx:
            services.quote_send(self.ada, 'USDT', Decimal('5'), recipient='bola')
        self.assertEqual(ctx.exception.code, 'network_required')
        self.assertIn('TRON, BNB Chain or Ethereum', ctx.exception.message)

    def test_coin_with_one_network_needs_no_choice(self):
        quote = services.quote_send(self.ada, 'SOL', Decimal('1'), recipient='bola', at=NOW)
        self.assertEqual(quote.network, 'SOL')
        self.assertGreater(quote.fee_amount, 0)

    def test_wrong_network_for_the_coin_is_refused(self):
        with self.assertRaises(WalletError) as ctx:
            services.quote_send(self.ada, 'BTC', Decimal('0.001'), recipient='bola', network='TRON')
        self.assertEqual(ctx.exception.code, 'invalid_network')

    def test_naira_is_free_and_has_no_network(self):
        quote = services.quote_send(self.ada, 'NGN', Decimal('5000'), recipient='bola', network='TRON')
        tx = services.execute_send(self.ada, quote)
        self.assertEqual((quote.fee_amount, quote.network), (Decimal(0), ''))
        self.assertEqual(tx.network, '')
        self.assertEqual(balance(self.bola, 'NGN'), Decimal('505000'))

    def test_external_send_charges_a_network_fee(self):
        quote = services.quote_send(self.ada, 'USDT', Decimal('50'), address=ADDRESS, network='BEP20', at=NOW)
        tx = services.execute_send(self.ada, quote)

        self.assertEqual(quote.fee_amount, Decimal('0.30'))
        self.assertEqual(balance(self.ada, 'USDT'), Decimal('199.70'))
        self.assertEqual(tx.address, ADDRESS)

    def test_fee_counts_towards_the_balance_check(self):
        quote = services.quote_send(self.ada, 'USDT', Decimal('250'), address=ADDRESS, network='TRC20', at=NOW)
        with self.assertRaises(WalletError) as ctx:
            services.execute_send(self.ada, quote)
        self.assertEqual(ctx.exception.code, 'insufficient_funds')
        self.assertEqual(balance(self.ada, 'USDT'), Decimal('250'))

    def test_bad_destinations_are_refused(self):
        cases = [
            ('unknown_recipient', {'recipient': 'nobody'}),
            ('invalid_destination', {'recipient': 'ada'}),
            ('invalid_destination', {'address': 'short'}),
            ('invalid_destination', {}),
            ('invalid_destination', {'recipient': 'bola', 'address': ADDRESS}),
        ]
        for code, destination in cases:
            with self.subTest(destination=destination):
                with self.assertRaises(WalletError) as ctx:
                    services.quote_send(self.ada, 'USDT', Decimal('1'), **destination)
                self.assertEqual(ctx.exception.code, code)

    def test_naira_cannot_leave_vira(self):
        with self.assertRaises(WalletError) as ctx:
            services.quote_send(self.ada, 'NGN', Decimal('1'), address=ADDRESS)
        self.assertEqual(ctx.exception.code, 'invalid_destination')


@mock.patch('market.simulator.time.time', return_value=NOW)
class WalletApiTests(APITestCase):
    def setUp(self):
        self.ada, self.bola = make_user('ada'), make_user('bola')
        self.client.force_authenticate(self.ada)

    def trade(self, **overrides):
        data = {'kind': 'buy', 'from_asset': 'ngn', 'to_asset': 'btc', 'amount': '20000', **overrides}
        return self.client.post(reverse('trade'), data)

    def test_endpoints_require_auth(self, _time):
        self.client.force_authenticate(None)
        for name in ['portfolio', 'transaction-list']:
            self.assertEqual(self.client.get(reverse(name)).status_code, status.HTTP_401_UNAUTHORIZED)
        for name in ['trade', 'trade-quote', 'send', 'send-quote']:
            self.assertEqual(self.client.post(reverse(name)).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_portfolio_shows_only_own_wallets_with_values(self, _time):
        Wallet.objects.filter(user=self.bola, asset='NGN').update(balance=1)

        response = self.client.get(reverse('portfolio'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows = {row['asset']: row for row in response.data['wallets']}
        self.assertEqual(rows['NGN']['balance'], '500000.00000000')
        self.assertEqual(rows['USDT']['value_usd'], '250.00')
        total = sum(Decimal(row['value_usd']) for row in response.data['wallets'])
        self.assertEqual(Decimal(response.data['total_usd']), total)

    def test_quote_changes_nothing(self, _time):
        response = self.client.post(reverse('trade-quote'), {
            'kind': 'buy', 'from_asset': 'NGN', 'to_asset': 'BTC', 'amount': '20000',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['has_balance'])
        self.assertEqual(balance(self.ada, 'NGN'), Decimal('500000'))
        self.assertFalse(Transaction.objects.exists())

    def test_quote_reports_when_balance_is_too_low(self, _time):
        response = self.client.post(reverse('trade-quote'), {
            'kind': 'buy', 'from_asset': 'NGN', 'to_asset': 'BTC', 'amount': '900000',
        })
        self.assertFalse(response.data['has_balance'])

    def test_trade_executes_and_summarises(self, _time):
        response = self.trade()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('with 20,000 NGN', response.data['summary'])
        self.assertEqual(balance(self.ada, 'NGN'), Decimal('480000'))

    def test_refused_trade_returns_message_and_code(self, _time):
        response = self.trade(amount='9000000')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'insufficient_funds')
        self.assertIn('500,000', response.data['detail'])

    def test_bad_amounts_are_rejected(self, _time):
        for amount in ['0', '-5', 'abc', 'NaN', '99999999999999999999']:
            with self.subTest(amount=amount):
                self.assertEqual(self.trade(amount=amount).status_code, status.HTTP_400_BAD_REQUEST)

    def test_largest_allowed_amount_does_not_crash(self, _time):
        response = self.client.post(reverse('trade-quote'), {
            'kind': 'buy', 'from_asset': 'NGN', 'to_asset': 'BTC', 'amount': '9999999999', 'amount_asset': 'BTC',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.post(reverse('trade-quote'), {
            'kind': 'sell', 'from_asset': 'BTC', 'to_asset': 'NGN', 'amount': '9999999999',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_send_and_history_for_both_users(self, _time):
        response = self.client.post(
            reverse('send'), {'asset': 'USDT', 'amount': '50', 'recipient': 'bola', 'network': 'TRC20'},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['summary'], 'Sent 50 USDT to @bola on TRON')

        self.client.force_authenticate(self.bola)
        rows = self.client.get(reverse('transaction-list')).data
        self.assertEqual(rows[0]['summary'], 'Received 50 USDT from @ada on TRON')

    def test_networks_list_gives_fees_in_the_coin(self, _time):
        networks = self.client.get(reverse('network-list')).data
        self.assertEqual([network['code'] for network in networks['USDT']], ['TRC20', 'BEP20', 'ERC20'])
        self.assertEqual(networks['USDT'][1]['fee_amount'], '0.30')
        self.assertEqual(len(networks['SOL']), 1)
        self.assertNotIn('NGN', networks)

    def test_send_quote_shows_recipient_without_their_email(self, _time):
        response = self.client.post(
            reverse('send-quote'), {'asset': 'USDT', 'amount': '50', 'recipient': 'bola', 'network': 'BEP20'},
        )
        self.assertEqual(response.data['network_name'], 'BNB Chain')
        self.assertEqual(response.data['total'], '50.30')
        self.assertEqual(response.data['recipient_name'], 'Bola')
        self.assertNotIn('bola@example.com', str(response.data))

    def test_history_filters_newest_first_and_limit(self, _time):
        self.trade()
        self.trade(kind='swap', from_asset='ETH', to_asset='SOL', amount='0.01')

        rows = self.client.get(reverse('transaction-list')).data
        self.assertEqual([row['kind'] for row in rows], ['swap', 'buy'])
        self.assertEqual(len(self.client.get(reverse('transaction-list'), {'kind': 'buy'}).data), 1)
        self.assertEqual(len(self.client.get(reverse('transaction-list'), {'asset': 'btc'}).data), 1)
        self.assertEqual(len(self.client.get(reverse('transaction-list'), {'limit': '1'}).data), 1)
        self.assertEqual(len(self.client.get(reverse('transaction-list'), {'limit': 'x'}).data), 2)

    def test_cannot_read_another_users_transaction(self, _time):
        reference = self.trade().data['reference']
        self.client.force_authenticate(self.bola)
        response = self.client.get(reverse('transaction-detail', args=[reference]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
