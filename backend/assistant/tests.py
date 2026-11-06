from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import anthropic
import requests
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.customers import add_customer
from wallets.models import Transaction, Wallet
from wallets.services import WalletError, balance_of, create_starting_wallets

from . import commands, drafts, intent as intent_module, speech
from .intent import Intent, _parse_with_rules, parse_intent
from .models import Draft, Turn
from .speakable import speakable
from .wake import strip_wake_word

User = get_user_model()

NOW = 1_800_000_000


def make_user(username, full_name=None):
    user = User.objects.create_user(
        username=username, email=f'{username}@example.com', password='x', full_name=full_name or username.title(),
    )
    create_starting_wallets(user)
    return user


def make_intent(action, **fields):
    return Intent(action=action, source='claude', **fields)


def buy_btc(**overrides):
    return make_intent('buy', **{'from_asset': 'NGN', 'to_asset': 'BTC', 'amount': '20000', 'amount_asset': 'NGN', **overrides})


class CommandTestCase(TestCase):
    def setUp(self):
        self.ada = make_user('ada', 'Ada Obi')
        self.tunde = make_user('tunde', 'Tunde Bello')

    def run_command(self, parsed, user=None, text='spoken text'):
        with mock.patch('assistant.commands.parse_intent', return_value=parsed) as parser:
            self.parser = parser
            reply, _ = commands.handle_command(user or self.ada, text)
        return reply


class DraftingTests(CommandTestCase):
    def test_trade_creates_a_draft_and_moves_nothing(self):
        reply = self.run_command(buy_btc())

        self.assertEqual(reply.kind, 'draft')
        self.assertIn('with 20,000 NGN', reply.text)
        self.assertIn('Tap approve', reply.text)
        self.assertEqual(reply.draft.status, 'pending')
        self.assertEqual(balance_of(self.ada, 'NGN'), Decimal('500000'))
        self.assertFalse(Transaction.objects.exists())

    def test_fraction_uses_the_real_balance(self):
        reply = self.run_command(make_intent('sell', from_asset='SOL', to_asset='NGN', fraction=0.5))
        self.assertEqual(Decimal(reply.draft.quote['from_amount']), Decimal('1'))

    def test_all_of_a_balance_can_be_spent(self):
        reply = self.run_command(make_intent('sell', from_asset='SOL', to_asset='NGN', fraction=1))
        drafts.approve_draft(self.ada, reply.draft.reference)
        self.assertEqual(balance_of(self.ada, 'SOL'), Decimal(0))

    def test_too_expensive_is_refused_without_a_draft(self):
        reply = self.run_command(buy_btc(amount='900000'))
        self.assertEqual(reply.kind, 'refused')
        self.assertIn("don't have enough NGN", reply.text)
        self.assertFalse(Draft.objects.exists())

    def test_missing_details_ask_a_question(self):
        cases = [
            (make_intent('buy', from_asset='NGN', amount='5000'), 'Which coin'),
            (make_intent('buy', from_asset='NGN', to_asset='BTC'), 'How much'),
            (make_intent('swap', amount='1'), 'Which two coins'),
            (make_intent('send', amount='5', recipient='tunde'), 'Which asset'),
            (make_intent('send', asset='USDT', amount='5'), 'Who would you like'),
            (make_intent('send', asset='USDT', recipient='tunde'), 'How much USDT'),
        ]
        for parsed, expected in cases:
            with self.subTest(expected=expected):
                reply = self.run_command(parsed)
                self.assertEqual(reply.kind, 'question')
                self.assertIn(expected, reply.text)
        self.assertFalse(Draft.objects.exists())

    def test_bad_values_from_the_parser_are_refused(self):
        cases = [
            buy_btc(amount='lots'),
            buy_btc(amount='-5'),
            buy_btc(amount='99999999999999'),
            buy_btc(amount=None, fraction=2),
            buy_btc(to_asset='NOPECOIN'),
            buy_btc(amount_asset='ETH'),
        ]
        for parsed in cases:
            with self.subTest(parsed=parsed):
                self.assertEqual(self.run_command(parsed).kind, 'refused')
        self.assertFalse(Draft.objects.exists())

    def test_send_matches_a_spoken_first_name(self):
        reply = self.run_command(make_intent('send', asset='USDT', amount='50', recipient='Tunde', network='TRON'))
        self.assertEqual(reply.draft.quote['recipient'], 'tunde')
        self.assertEqual(reply.draft.quote['network'], 'TRC20')
        self.assertIn('Tunde Bello', reply.text)
        self.assertIn('on TRON, plus a 1 USDT network fee', reply.text)

    def test_send_asks_which_network_when_there_is_a_choice(self):
        reply = self.run_command(make_intent('send', asset='USDT', amount='50', recipient='tunde'))
        self.assertEqual(reply.kind, 'question')
        self.assertIn('TRON, BNB Chain or Ethereum', reply.text)
        self.assertFalse(Draft.objects.exists())

    def test_send_picks_the_only_network_and_naira_has_none(self):
        coin = self.run_command(make_intent('send', asset='SOL', amount='1', recipient='tunde'))
        self.assertEqual(coin.draft.quote['network'], 'SOL')
        naira = self.run_command(make_intent('send', asset='NGN', amount='5000', recipient='tunde'))
        self.assertIsNone(naira.draft.quote['network'])
        self.assertEqual(naira.text, 'Send 5,000 NGN to Tunde Bello, username tunde. Tap approve to confirm.')

    def test_saved_customer_wins_over_a_stranger_with_a_similar_name(self):
        make_user('tunde2', 'Tunde Ade')
        self.assertEqual(self.run_command(make_intent('send', asset='NGN', amount='5', recipient='Bola')).kind, 'refused')
        self.assertEqual(self.run_command(make_intent('send', asset='NGN', amount='5', recipient='tun')).kind, 'question')

        add_customer(self.ada, 'tunde2')
        reply = self.run_command(make_intent('send', asset='NGN', amount='5', recipient='tun'))
        self.assertEqual(reply.draft.quote['recipient'], 'tunde2')

    def test_adding_a_customer_by_voice(self):
        reply = self.run_command(make_intent('add_customer', recipient='tunde'))
        self.assertIn('Tunde Bello', reply.text)
        self.assertEqual(self.ada.customers.get().user, self.tunde)
        self.assertEqual(self.run_command(make_intent('add_customer', recipient='tunde')).kind, 'refused')
        self.assertEqual(self.run_command(make_intent('add_customer')).kind, 'question')
        missing = self.run_command(make_intent('add_customer', recipient='nobody'))
        self.assertIn('sign up', missing.text)

    def test_listing_customers(self):
        self.assertIn("haven't saved", self.run_command(make_intent('list_customers')).text)
        add_customer(self.ada, 'tunde')
        self.assertIn('Tunde Bello', self.run_command(make_intent('list_customers')).text)

    def test_ambiguous_name_asks_which_one(self):
        make_user('tunde2', 'Tunde Ade')
        reply = self.run_command(make_intent('send', asset='USDT', amount='50', recipient='bello tunde', network='TRC20'))
        self.assertEqual(reply.kind, 'refused')
        reply = self.run_command(make_intent('send', asset='USDT', amount='50', recipient='tun', network='TRC20'))
        self.assertEqual(reply.kind, 'question')
        self.assertIn('Tunde Ade', reply.text)
        self.assertIn('Tunde Bello', reply.text)

    def test_unknown_recipient_and_self_send_are_refused(self):
        self.assertEqual(self.run_command(make_intent('send', asset='NGN', amount='5', recipient='nobody')).kind, 'refused')
        self.assertEqual(self.run_command(make_intent('send', asset='NGN', amount='5', recipient='ada')).kind, 'refused')

    def test_new_draft_replaces_the_open_one(self):
        first = self.run_command(buy_btc()).draft
        second = self.run_command(buy_btc(amount='1000')).draft
        first.refresh_from_db()
        self.assertEqual(first.status, 'rejected')
        self.assertEqual(second.status, 'pending')


class AnswerTests(CommandTestCase):
    def test_price_answer_uses_simulated_data(self):
        with mock.patch('market.simulator.time.time', return_value=NOW):
            reply = self.run_command(make_intent('get_price', asset='BTC'))
        self.assertEqual(reply.kind, 'answer')
        self.assertIn('Bitcoin is at', reply.text)
        self.assertIn(reply.data['symbol'], 'BTC')
        self.assertFalse(Draft.objects.exists())

    def test_balance_and_portfolio(self):
        self.assertIn('You have 250 USDT', self.run_command(make_intent('get_balance', asset='USDT')).text)
        self.assertIn("don't have any DOGE", self.run_command(make_intent('get_balance', asset='DOGE')).text)
        self.assertIn('You have 500,000 naira', self.run_command(make_intent('get_balance', asset='NGN')).text)
        self.assertIn('portfolio is worth', self.run_command(make_intent('get_portfolio')).text)

    def test_history_lists_recent_and_filters_by_day(self):
        self.assertIn("don't have any transactions", self.run_command(make_intent('get_history')).text)

        draft = self.run_command(buy_btc()).draft
        drafts.approve_draft(self.ada, draft.reference)

        self.assertIn('Bought', self.run_command(make_intent('get_history')).text)
        self.assertIn('Bought', self.run_command(make_intent('get_history', history_days_ago=0, asset='BTC')).text)
        self.assertIn('yesterday', self.run_command(make_intent('get_history', history_days_ago=1)).text)

    def test_saying_yes_never_approves(self):
        draft = self.run_command(buy_btc()).draft

        reply = self.run_command(make_intent('voice_approval'))

        self.assertIn("can't approve by voice", reply.text)
        draft.refresh_from_db()
        self.assertEqual(draft.status, 'pending')
        self.assertEqual(balance_of(self.ada, 'NGN'), Decimal('500000'))

    def test_cancel_by_voice(self):
        draft = self.run_command(buy_btc()).draft
        self.assertIn('cancelled', self.run_command(make_intent('cancel')).text)
        draft.refresh_from_db()
        self.assertEqual(draft.status, 'rejected')
        self.assertIn('nothing to cancel', self.run_command(make_intent('cancel')).text)

    def test_unsupported_uses_a_default_if_no_message(self):
        self.assertIn('I can help', self.run_command(make_intent('unsupported')).text)


class FollowUpTests(CommandTestCase):
    def test_unanswered_question_is_passed_as_history(self):
        self.run_command(make_intent('send', asset='USDT', recipient='tunde'), text='send usdt to tunde')
        self.run_command(make_intent('send', asset='USDT', amount='50', recipient='tunde'), text='fifty')

        _, history = self.parser.call_args.args
        self.assertEqual([turn.text for turn in history], ['send usdt to tunde'])

    def test_answered_turn_ends_the_chain(self):
        self.run_command(make_intent('send', asset='USDT'), text='first')
        self.run_command(make_intent('get_portfolio'), text='second')
        self.run_command(make_intent('get_portfolio'), text='third')
        _, history = self.parser.call_args.args
        self.assertEqual(history, [])

    def test_old_questions_are_ignored(self):
        self.run_command(make_intent('send', asset='USDT'), text='first')
        Turn.objects.update(created_at=timezone.now() - timedelta(minutes=5))
        self.run_command(make_intent('get_portfolio'), text='second')
        _, history = self.parser.call_args.args
        self.assertEqual(history, [])


class ApprovalTests(CommandTestCase):
    def draft(self, parsed=None):
        return self.run_command(parsed or buy_btc()).draft

    def test_approve_executes_the_quote_shown_even_if_price_moved(self):
        with mock.patch('market.simulator.time.time', return_value=NOW):
            draft = self.draft()
        shown = Decimal(draft.quote['to_amount'])
        btc_before = balance_of(self.ada, 'BTC')

        with mock.patch('market.simulator.time.time', return_value=NOW + 30):
            approved = drafts.approve_draft(self.ada, draft.reference)

        self.assertEqual(approved.status, 'executed')
        self.assertEqual(approved.transaction.to_amount, shown)
        self.assertEqual(balance_of(self.ada, 'BTC'), btc_before + shown)
        self.assertEqual(balance_of(self.ada, 'NGN'), Decimal('480000'))

    def test_double_approve_only_executes_once(self):
        draft = self.draft()
        first = drafts.approve_draft(self.ada, draft.reference)
        second = drafts.approve_draft(self.ada, draft.reference)
        self.assertEqual(first.transaction_id, second.transaction_id)
        self.assertEqual(self.ada.transactions.count(), 1)
        self.assertEqual(balance_of(self.ada, 'NGN'), Decimal('480000'))

    def test_expired_draft_cannot_be_approved(self):
        draft = self.draft()
        Draft.objects.update(expires_at=timezone.now() - timedelta(seconds=1))

        with self.assertRaises(WalletError) as ctx:
            drafts.approve_draft(self.ada, draft.reference)

        self.assertEqual(ctx.exception.code, 'draft_expired')
        draft.refresh_from_db()
        self.assertEqual(draft.status, 'expired')
        self.assertEqual(balance_of(self.ada, 'NGN'), Decimal('500000'))

    def test_rejected_draft_cannot_be_approved(self):
        draft = self.draft()
        drafts.reject_draft(self.ada, draft.reference)
        with self.assertRaises(WalletError) as ctx:
            drafts.approve_draft(self.ada, draft.reference)
        self.assertEqual(ctx.exception.code, 'draft_closed')

    def test_executed_draft_cannot_be_rejected(self):
        draft = self.draft()
        drafts.approve_draft(self.ada, draft.reference)
        with self.assertRaises(WalletError):
            drafts.reject_draft(self.ada, draft.reference)

    def test_funds_spent_after_drafting_fail_cleanly(self):
        draft = self.draft()
        Wallet.objects.filter(user=self.ada, asset='NGN').update(balance=5)

        with self.assertRaises(WalletError) as ctx:
            drafts.approve_draft(self.ada, draft.reference)

        self.assertEqual(ctx.exception.code, 'insufficient_funds')
        draft.refresh_from_db()
        self.assertEqual(draft.status, 'failed')
        self.assertEqual(balance_of(self.ada, 'NGN'), Decimal('5'))
        self.assertFalse(Transaction.objects.exists())

    def test_approving_a_send_moves_funds_to_the_recipient(self):
        draft = self.draft(make_intent('send', asset='USDT', amount='50', recipient='tunde', network='BEP20'))
        approved = drafts.approve_draft(self.ada, draft.reference)
        self.assertEqual(approved.transaction.network, 'BEP20')
        self.assertEqual(balance_of(self.ada, 'USDT'), Decimal('199.70'))
        self.assertEqual(balance_of(self.tunde, 'USDT'), Decimal('300'))

    def test_approving_an_external_send_charges_the_quoted_fee(self):
        address = 'bc1qxy2kgdygjrsqtzq2n0yrf2493p83kk'
        draft = self.draft(make_intent('send', asset='USDT', amount='50', address=address, network='TRC20'))
        approved = drafts.approve_draft(self.ada, draft.reference)
        self.assertEqual(approved.transaction.address, address)
        self.assertEqual(balance_of(self.ada, 'USDT'), Decimal('199'))


class AssistantApiTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.ada, self.bola = make_user('ada'), make_user('bola')
        self.client.force_authenticate(self.ada)

    def post_command(self, parsed):
        with mock.patch('assistant.commands.parse_intent', return_value=parsed):
            return self.client.post(reverse('assistant-command'), {'text': 'buy some bitcoin'})

    def test_everything_requires_auth(self):
        self.client.force_authenticate(None)
        for name in ['assistant-command', 'assistant-voice', 'assistant-speak']:
            self.assertEqual(self.client.post(reverse(name)).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.get(reverse('draft-list')).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_command_returns_draft_then_approve_executes(self):
        response = self.post_command(buy_btc())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['type'], 'draft')
        self.assertEqual(response.data['parser'], 'claude')
        reference = response.data['draft']['reference']

        approved = self.client.post(reverse('draft-approve', args=[reference]))

        self.assertEqual(approved.status_code, status.HTTP_200_OK)
        self.assertIn('Done. Bought', approved.data['reply'])
        self.assertEqual(approved.data['draft']['status'], 'executed')
        self.assertEqual(approved.data['draft']['transaction']['kind'], 'buy')

    def test_another_user_cannot_touch_my_draft(self):
        reference = self.post_command(buy_btc()).data['draft']['reference']
        self.client.force_authenticate(self.bola)

        for name in ['draft-approve', 'draft-reject']:
            response = self.client.post(reverse(name, args=[reference]))
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.get(reverse('draft-detail', args=[reference])).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.get(reverse('draft-list')).data, [])
        self.assertEqual(balance_of(self.ada, 'NGN'), Decimal('500000'))

    def test_expired_draft_returns_clear_error_and_status(self):
        reference = self.post_command(buy_btc()).data['draft']['reference']
        Draft.objects.update(expires_at=timezone.now() - timedelta(seconds=1))

        self.assertEqual(self.client.get(reverse('draft-detail', args=[reference])).data['status'], 'expired')
        response = self.client.post(reverse('draft-approve', args=[reference]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'draft_expired')

    def test_reject_endpoint(self):
        reference = self.post_command(buy_btc()).data['draft']['reference']
        response = self.client.post(reverse('draft-reject', args=[reference]))
        self.assertEqual(response.data['draft']['status'], 'rejected')

    def test_blank_and_oversized_text_are_rejected(self):
        for text in ['', 'x' * 501]:
            response = self.client.post(reverse('assistant-command'), {'text': text})
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def audio(self, content_type='audio/webm', size=10):
        return SimpleUploadedFile('clip.webm', b'x' * size, content_type=content_type)

    def test_voice_transcribes_then_drafts(self):
        with mock.patch('assistant.speech.transcribe', return_value='buy 20k naira of bitcoin') as transcribe, \
                mock.patch('assistant.commands.parse_intent', return_value=buy_btc()):
            response = self.client.post(reverse('assistant-voice'), {'audio': self.audio()}, format='multipart')

        transcribe.assert_called_once()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['transcript'], 'buy 20k naira of bitcoin')
        self.assertEqual(response.data['type'], 'draft')
        self.assertEqual(response.data['draft']['transcript'], 'buy 20k naira of bitcoin')

    def test_voice_with_no_speech_asks_again(self):
        with mock.patch('assistant.speech.transcribe', return_value=''), \
                mock.patch('assistant.commands.parse_intent') as parser:
            response = self.client.post(reverse('assistant-voice'), {'audio': self.audio()}, format='multipart')
        self.assertIn("didn't catch", response.data['reply'])
        parser.assert_not_called()

    def test_voice_rejects_non_audio_and_oversized_files(self):
        with mock.patch('assistant.speech.transcribe') as transcribe:
            response = self.client.post(
                reverse('assistant-voice'), {'audio': self.audio('text/plain')}, format='multipart',
            )
            self.assertEqual(response.data['code'], 'invalid_audio')
            with override_settings(MAX_AUDIO_UPLOAD_BYTES=5):
                response = self.client.post(reverse('assistant-voice'), {'audio': self.audio()}, format='multipart')
            self.assertEqual(response.data['code'], 'audio_too_large')
        transcribe.assert_not_called()

    def test_speech_outage_returns_502_without_details(self):
        with mock.patch('assistant.speech.transcribe', side_effect=speech.SpeechError('secret detail')):
            response = self.client.post(reverse('assistant-voice'), {'audio': self.audio()}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(response.data['code'], 'speech_unavailable')
        self.assertNotIn('secret detail', str(response.data))

    def test_speak_returns_audio(self):
        with mock.patch('assistant.speech.synthesize', return_value=b'mp3-bytes') as synthesize:
            response = self.client.post(reverse('assistant-speak'), {'text': 'Buy 5 BTC'})
        synthesize.assert_called_once_with('Buy 5 Bitcoin')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'audio/mpeg')
        self.assertEqual(response.content, b'mp3-bytes')

    def test_throttle_applies_to_paid_endpoints(self):
        with mock.patch('assistant.views.ScopedRateThrottle.THROTTLE_RATES', {'assistant': '2/min'}), \
                mock.patch('assistant.speech.synthesize', return_value=b'x'):
            codes = [self.client.post(reverse('assistant-speak'), {'text': 'Hi'}).status_code for _ in range(3)]
        self.assertEqual(codes, [200, 200, 429])


class ManualTradeDraftTests(APITestCase):
    def setUp(self):
        self.ada, self.bola = make_user('ada'), make_user('bola')
        self.client.force_authenticate(self.ada)

    def create(self, **overrides):
        data = {'kind': 'buy', 'from_asset': 'NGN', 'to_asset': 'BTC', 'amount': '20000', **overrides}
        return self.client.post(reverse('draft-list'), data)

    def test_requires_auth(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.create().status_code, status.HTTP_401_UNAUTHORIZED)

    def test_draft_moves_nothing_until_approved_at_the_locked_amounts(self):
        with mock.patch('market.simulator.time.time', return_value=NOW):
            response = self.create()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'pending')
        self.assertEqual(response.data['action'], 'buy')
        self.assertEqual(balance_of(self.ada, 'NGN'), Decimal('500000'))
        shown = Decimal(response.data['quote']['to_amount'])
        btc_before = balance_of(self.ada, 'BTC')

        with mock.patch('market.simulator.time.time', return_value=NOW + 30):
            approved = self.client.post(reverse('draft-approve', args=[response.data['reference']]))

        self.assertEqual(approved.status_code, status.HTTP_200_OK)
        self.assertEqual(approved.data['draft']['status'], 'executed')
        self.assertEqual(balance_of(self.ada, 'NGN'), Decimal('480000'))
        self.assertEqual(balance_of(self.ada, 'BTC'), btc_before + shown)

    def test_sell_and_swap(self):
        sold = self.client.post(reverse('draft-approve', args=[
            self.create(kind='sell', from_asset='SOL', to_asset='USDT', amount='1').data['reference'],
        ]))
        self.assertEqual(sold.status_code, status.HTTP_200_OK)
        self.assertEqual(balance_of(self.ada, 'SOL'), Decimal('1'))

        swapped = self.client.post(reverse('draft-approve', args=[
            self.create(kind='swap', from_asset='ETH', to_asset='DOGE', amount='0.05').data['reference'],
        ]))
        self.assertEqual(swapped.status_code, status.HTTP_200_OK)
        self.assertEqual(balance_of(self.ada, 'ETH'), Decimal('0.05'))
        self.assertGreater(balance_of(self.ada, 'DOGE'), 0)

    def test_amount_can_be_given_in_the_coin_received(self):
        response = self.create(amount='0.001', amount_asset='BTC')
        self.assertEqual(Decimal(response.data['quote']['to_amount']), Decimal('0.001'))

    def test_refusals_create_no_draft(self):
        cases = [
            ('insufficient_funds', {'amount': '900000'}),
            ('invalid_pair', {'kind': 'swap', 'from_asset': 'NGN'}),
            ('unknown_asset', {'to_asset': 'NOPE'}),
        ]
        for code, overrides in cases:
            with self.subTest(code=code):
                response = self.create(**overrides)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(response.data['code'], code)
        self.assertEqual(self.create(amount='-5').status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Draft.objects.exists())

    def test_new_trade_replaces_an_open_draft(self):
        first = self.create().data['reference']
        self.create(amount='1000')
        self.assertEqual(Draft.objects.get(reference=first).status, 'rejected')


class ManualSendDraftTests(APITestCase):
    def setUp(self):
        self.ada, self.tunde = make_user('ada'), make_user('tunde')
        self.client.force_authenticate(self.ada)

    def create(self, **overrides):
        data = {'asset': 'USDT', 'amount': '15', 'recipient': 'tunde', 'network': 'TRC20', **overrides}
        return self.client.post(reverse('draft-send'), data)

    def test_requires_auth(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.create().status_code, status.HTTP_401_UNAUTHORIZED)

    def test_nothing_moves_until_approved_then_recipient_is_paid(self):
        response = self.create()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['quote']['network_name'], 'TRON')
        self.assertEqual(balance_of(self.ada, 'USDT'), Decimal('250'))

        approved = self.client.post(reverse('draft-approve', args=[response.data['reference']]))

        self.assertEqual(approved.status_code, status.HTTP_200_OK)
        self.assertIn('on TRON', approved.data['reply'])
        self.assertEqual(balance_of(self.ada, 'USDT'), Decimal('234'))
        self.assertEqual(balance_of(self.tunde, 'USDT'), Decimal('265'))

    def test_refusals_create_no_draft(self):
        cases = [
            ('network_required', {'network': ''}),
            ('invalid_network', {'network': 'Solana'}),
            ('insufficient_funds', {'amount': '250'}),
            ('unknown_recipient', {'recipient': 'nobody'}),
        ]
        for code, overrides in cases:
            with self.subTest(code=code):
                response = self.create(**overrides)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(response.data['code'], code)
        self.assertFalse(Draft.objects.exists())


class SpeakableTests(SimpleTestCase):
    def test_rewrites_amounts_and_assets_for_speech(self):
        cases = [
            (
                'Buy 0.0001337 BTC with 20,000 NGN, including a 100 NGN fee.',
                'Buy zero point zero zero zero one three three seven Bitcoin with 20,000 naira, including a 100 naira fee.',
            ),
            ('Buy 0.01564271 SOL now', 'Buy about zero point zero one five six four Solana now'),
            ('Sell 0.05 ETH for 252,199.5 NGN.', 'Sell zero point zero five Ethereum for about 252,000 naira.'),
            ('Swap to 146.14501241 DOGE.', 'Swap to about 146 point one five Dogecoin.'),
            ('You have 250 USDT, worth about 250.00 dollars.', 'You have 250 U S D T, worth about 250 dollars.'),
            ('Send 15 USDT to Tunde.', 'Send 15 U S D T to Tunde.'),
            (
                'Bitcoin is at 95,133.26 dollars, about 148,293,958 naira.',
                'Bitcoin is at about 95,100 dollars, about 148 million naira.',
            ),
            ('Worth 2,765,933 NGN.', 'Worth about 2 point seven seven million naira.'),
            ('Send 5 USDT to the address ending in 1234.', 'Send 5 U S D T to the address ending in 1234.'),
            ('Send 2 SOL to tunde2.', 'Send 2 Solana to tunde2.'),
            ('Buy with 20,000 NGN.', 'Buy with 20,000 naira.'),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(speakable(text), expected)

    def test_rounding_never_drops_to_nothing(self):
        self.assertIn('zero point zero zero zero zero zero zero zero one', speakable('Fee 0.00000001 BTC'))

    def test_leaves_other_words_alone(self):
        self.assertEqual(speakable('To keep your funds safe, tap approve.'), 'To keep your funds safe, tap approve.')


class WakeWordTests(SimpleTestCase):
    def test_recognises_wake_word_and_likely_mishearings(self):
        cases = [
            ('Vira', ''),
            ('Hey Vira.', ''),
            ('hey vera, buy 20k naira of bitcoin', 'buy 20k naira of bitcoin'),
            ('Okay, Veera what is my balance?', 'what is my balance?'),
            ('[background noise] Hey Vira sell half my ETH', 'sell half my ETH'),
            ('um hey vira send 5 USDT to Tunde', 'send 5 USDT to Tunde'),
        ]
        for text, rest in cases:
            with self.subTest(text=text):
                self.assertEqual(strip_wake_word(text), (True, rest))

    def test_ignores_speech_without_it(self):
        cases = ['buy some bitcoin', 'I told Vira about it', 'veranda', 'hey there', 'hey', '', '[music]']
        for text in cases:
            with self.subTest(text=text):
                self.assertFalse(strip_wake_word(text)[0])


class WakeWordApiTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.ada = make_user('ada')
        self.client.force_authenticate(self.ada)

    def speak(self, transcript, wake_word=True):
        audio = SimpleUploadedFile('clip.webm', b'x', content_type='audio/webm')
        with mock.patch('assistant.speech.transcribe', return_value=transcript), \
                mock.patch('assistant.commands.parse_intent', return_value=buy_btc()) as self.parser:
            return self.client.post(
                reverse('assistant-voice'), {'audio': audio, 'wake_word': wake_word}, format='multipart',
            )

    def test_speech_without_wake_word_is_dropped_before_claude(self):
        response = self.speak('did you see the game last night')
        self.assertEqual(response.data['type'], 'ignored')
        self.assertEqual(response.data['transcript'], '')
        self.parser.assert_not_called()
        self.assertFalse(Turn.objects.exists())

    def test_silence_is_ignored_in_hands_free_mode(self):
        self.assertEqual(self.speak('').data['type'], 'ignored')

    def test_wake_word_with_command_runs_it_without_the_wake_word(self):
        response = self.speak('Hey Vira, buy 20k naira of bitcoin')
        self.assertEqual(response.data['type'], 'draft')
        self.assertEqual(response.data['draft']['transcript'], 'buy 20k naira of bitcoin')
        self.assertEqual(self.parser.call_args.args[0], 'buy 20k naira of bitcoin')

    def test_wake_word_alone_starts_listening(self):
        response = self.speak('Hey Vira.')
        self.assertEqual(response.data['type'], 'listening')
        self.parser.assert_not_called()

    def test_mic_button_mode_does_not_need_it(self):
        self.assertEqual(self.speak('buy 20k naira of bitcoin', wake_word=False).data['type'], 'draft')

    def test_wake_word_cannot_approve(self):
        self.parser_intent = make_intent('voice_approval')
        draft = self.speak('Hey Vira, buy 20k naira of bitcoin').data['draft']
        audio = SimpleUploadedFile('clip.webm', b'x', content_type='audio/webm')
        with mock.patch('assistant.speech.transcribe', return_value='Hey Vira, yes approve it'), \
                mock.patch('assistant.commands.parse_intent', return_value=make_intent('voice_approval')):
            response = self.client.post(
                reverse('assistant-voice'), {'audio': audio, 'wake_word': True}, format='multipart',
            )
        self.assertIn("can't approve by voice", response.data['reply'])
        self.assertEqual(Draft.objects.get(reference=draft['reference']).status, 'pending')

    def test_typed_commands_tolerate_it_too(self):
        with mock.patch('assistant.commands.parse_intent', return_value=buy_btc()) as parser:
            self.client.post(reverse('assistant-command'), {'text': 'hey vira buy bitcoin'})
        self.assertEqual(parser.call_args.args[0], 'buy bitcoin')


class SpeechClientTests(SimpleTestCase):
    def response(self, code=200, **fields):
        result = requests.Response()
        result.status_code = code
        result._content = fields.get('content', b'')
        return result

    @override_settings(ELEVENLABS_API_KEY='test-key')
    def test_transcribe_sends_expected_request(self):
        upload = SimpleUploadedFile('clip.webm', b'abc', content_type='audio/webm')
        with mock.patch.object(speech._session, 'post', return_value=self.response(content=b'{"text": " hello "}')) as post:
            self.assertEqual(speech.transcribe(upload), 'hello')
        self.assertIn('/speech-to-text', post.call_args.args[0])
        self.assertEqual(post.call_args.kwargs['headers']['xi-api-key'], 'test-key')
        self.assertEqual(post.call_args.kwargs['data']['model_id'], 'scribe_v2')

    @override_settings(ELEVENLABS_API_KEY='test-key', ELEVENLABS_VOICE_ID='voice1')
    def test_synthesize_returns_audio_and_errors_hide_the_key(self):
        with mock.patch.object(speech._session, 'post', return_value=self.response(content=b'mp3')) as post:
            self.assertEqual(speech.synthesize('hi'), b'mp3')
        self.assertIn('/text-to-speech/voice1', post.call_args.args[0])

        with mock.patch.object(speech._session, 'post', return_value=self.response(401, content=b'bad')):
            with self.assertRaises(speech.SpeechError) as ctx:
                speech.synthesize('hi')
        self.assertIn('401', str(ctx.exception))
        self.assertNotIn('test-key', str(ctx.exception))

    @override_settings(ELEVENLABS_API_KEY='test-key')
    def test_dropped_connection_is_retried_once_with_the_file_rewound(self):
        sent = []

        def post(url, files, **kwargs):
            sent.append(files['file'][1].read())
            if len(sent) == 1:
                raise requests.ConnectionError
            return self.response(content=b'{"text": "hello"}')

        upload = SimpleUploadedFile('clip.webm', b'abc', content_type='audio/webm')
        with mock.patch.object(speech._session, 'post', side_effect=post):
            self.assertEqual(speech.transcribe(upload), 'hello')
        self.assertEqual(sent, [b'abc', b'abc'])

    @override_settings(ELEVENLABS_API_KEY='test-key', ELEVENLABS_VOICE_ID='voice1')
    def test_second_connection_failure_is_a_speech_error(self):
        with mock.patch.object(speech._session, 'post', side_effect=requests.ConnectionError) as post:
            with self.assertRaises(speech.SpeechError):
                speech.synthesize('hi')
        self.assertEqual(post.call_count, 2)

    @override_settings(ELEVENLABS_API_KEY='')
    def test_missing_key_is_a_speech_error(self):
        with self.assertRaises(speech.SpeechError):
            speech.synthesize('hi')


CLAUDE_JSON = (
    '{"action": "buy", "from_asset": "naira", "to_asset": "Bitcoin", "asset": null, "amount": "20000", '
    '"amount_asset": "ngn", "fraction": null, "recipient": null, "address": null, "network": null, '
    '"history_days_ago": null, "message": null}'
)


class ClaudeParserTests(SimpleTestCase):
    def setUp(self):
        self.addCleanup(setattr, intent_module, '_client', None)

    def fake_client(self, **response_fields):
        client = mock.Mock()
        client.beta.messages.create.return_value = SimpleNamespace(**response_fields)
        intent_module._client = client
        return client

    @override_settings(ANTHROPIC_API_KEY='test-key')
    def test_parses_and_normalizes_output(self):
        client = self.fake_client(
            stop_reason='end_turn',
            content=[SimpleNamespace(type='thinking'), SimpleNamespace(type='text', text=CLAUDE_JSON)],
        )
        parsed = parse_intent('buy 20k naira of bitcoin')

        self.assertEqual((parsed.source, parsed.action), ('claude', 'buy'))
        self.assertEqual((parsed.from_asset, parsed.to_asset, parsed.amount_asset), ('NGN', 'BTC', 'NGN'))
        request = client.beta.messages.create.call_args.kwargs
        self.assertEqual(request['fallbacks'], 'default')
        self.assertEqual(request['output_config']['format']['type'], 'json_schema')

    @override_settings(ANTHROPIC_API_KEY='test-key')
    def test_history_is_sent_as_conversation(self):
        client = self.fake_client(stop_reason='end_turn', content=[SimpleNamespace(type='text', text=CLAUDE_JSON)])
        history = [SimpleNamespace(text='send usdt to tunde', reply='How much USDT would you like to send?')]

        parse_intent('fifty', history)

        roles = [(m['role'], m['content']) for m in client.beta.messages.create.call_args.kwargs['messages']]
        self.assertEqual(roles, [
            ('user', 'send usdt to tunde'),
            ('assistant', 'How much USDT would you like to send?'),
            ('user', 'fifty'),
        ])

    @override_settings(ANTHROPIC_API_KEY='test-key')
    def test_falls_back_on_api_error_refusal_and_bad_output(self):
        request = mock.Mock()
        outcomes = [
            {'side_effect': anthropic.APIConnectionError(request=request)},
            {'return_value': SimpleNamespace(stop_reason='refusal', content=[])},
            {'return_value': SimpleNamespace(stop_reason='end_turn', content=[SimpleNamespace(type='text', text='nope')])},
            {'return_value': SimpleNamespace(stop_reason='end_turn', content=[])},
        ]
        for outcome in outcomes:
            with self.subTest(outcome=outcome):
                client = mock.Mock()
                client.beta.messages.create.configure_mock(**outcome)
                intent_module._client = client
                with self.assertLogs('assistant.intent', 'WARNING'):
                    parsed = parse_intent('price of solana')
                self.assertEqual((parsed.source, parsed.action, parsed.asset), ('fallback', 'get_price', 'SOL'))

    @override_settings(ANTHROPIC_API_KEY='')
    def test_missing_key_falls_back(self):
        with self.assertLogs('assistant.intent', 'WARNING'):
            self.assertEqual(parse_intent('whats my balance').source, 'fallback')


class RuleParserTests(SimpleTestCase):
    def check(self, text, **expected):
        parsed = _parse_with_rules(text)
        for field, value in expected.items():
            self.assertEqual(getattr(parsed, field), value, f'{text}: {field}')

    def test_commands(self):
        self.check('Buy 20k naira of bitcoin.', action='buy', from_asset='NGN', to_asset='BTC', amount='20000', amount_asset='NGN')
        self.check('buy 0.01 btc', action='buy', from_asset='NGN', to_asset='BTC', amount='0.01', amount_asset='BTC')
        self.check('buy 50 usdt of solana', action='buy', from_asset='USDT', to_asset='SOL', amount='50', amount_asset='USDT')
        self.check('buy 1.5m naira of eth', amount='1500000', to_asset='ETH')
        self.check('sell half my eth', action='sell', from_asset='ETH', to_asset='NGN', fraction=0.5)
        self.check('sell 2 sol for usdt', action='sell', from_asset='SOL', to_asset='USDT', amount='2')
        self.check('swap 0.05 eth to sol', action='swap', from_asset='ETH', to_asset='SOL', amount='0.05')
        self.check('send 50 usdt to @Tunde', action='send', asset='USDT', amount='50', recipient='tunde')
        self.check('send 50 usdt to tunde on tron', action='send', recipient='tunde', network='tron')
        self.check('send 5 usdt to tunde via the bnb chain network', recipient='tunde', network='bnb chain network')
        self.check('add tunde as a customer', action='add_customer', recipient='tunde')
        self.check('who are my customers', action='list_customers')
        self.check("what's the price of solana?", action='get_price', asset='SOL')
        self.check('how much usdt do i have', action='get_balance', asset='USDT')
        self.check("what's my balance", action='get_portfolio')
        self.check('show my transactions', action='get_history')
        self.check('never mind', action='cancel')
        self.check('Yes.', action='voice_approval')
        self.check('tell me a joke', action='unsupported')
