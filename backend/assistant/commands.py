"""
Handles one thing the user said: understand it, then answer it or draft it.

Replies are built here from real data rather than written by Claude, so a spoken
price or amount always matches what the backend will actually do.
"""

import re
from datetime import datetime, time, timedelta
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from market import simulator
from market.views import price_row
from wallets import services
from wallets.serializers import TransactionSerializer
from wallets.services import WalletError, format_amount

from . import drafts
from .intent import parse_intent
from .models import Draft, Turn

User = get_user_model()

MAX_AMOUNT = Decimal('9999999999')
FOLLOW_UP_WINDOW = timedelta(minutes=2)
MAX_FOLLOW_UP_TURNS = 4
SPOKEN_HISTORY_LIMIT = 3
AMOUNT_PATTERN = re.compile(r'^\d+(\.\d{1,8})?$')


class Reply:
    """What goes back to the frontend, and what the next turn needs to know."""

    def __init__(self, kind, text, draft=None, data=None, follow_up=False):
        self.kind = kind
        self.text = text
        self.draft = draft
        self.data = data
        self.follow_up = follow_up


def _question(text):
    return Reply('question', text, follow_up=True)


def _answer(text, data=None):
    return Reply('answer', text, data=data)


def _follow_up_history(user):
    """Recent unanswered questions from Vira, oldest first, so "50 USDT" can complete "send how much?"."""
    recent = user.assistant_turns.filter(created_at__gte=timezone.now() - FOLLOW_UP_WINDOW)
    history = []
    for turn in recent[:MAX_FOLLOW_UP_TURNS]:
        if not turn.needs_follow_up:
            break
        history.append(turn)
    return list(reversed(history))


def _parse_amount(intent, balance_asset, user):
    """Returns (amount, asset it's in). A share of a balance becomes a real number here."""
    if intent.fraction is not None:
        fraction = Decimal(str(intent.fraction))
        if not 0 < fraction <= 1:
            raise WalletError('invalid_amount', "I can only use up to your whole balance.")
        balance = services.balance_of(user, balance_asset)
        if balance <= 0:
            raise WalletError('insufficient_funds', f"You don't have any {balance_asset}.")
        return (balance * fraction).quantize(Decimal('0.00000001'), rounding=ROUND_DOWN), balance_asset

    if not intent.amount:
        return None, None
    cleaned = intent.amount.replace(',', '').strip()
    if not AMOUNT_PATTERN.match(cleaned):
        raise WalletError('invalid_amount', "I didn't catch a valid amount.")
    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise WalletError('invalid_amount', "I didn't catch a valid amount.") from exc
    if not 0 < amount <= MAX_AMOUNT:
        raise WalletError('invalid_amount', "That amount isn't one I can use.")
    return amount, intent.amount_asset or balance_asset


def _not_enough(user, asset, needed):
    have = services.balance_of(user, asset)
    return Reply(
        'refused',
        f"You don't have enough {asset} for that. It needs {format_amount(needed)}, and you have {format_amount(have)}.",
    )


def _trade_summary(quote):
    paid = f'{format_amount(quote.from_amount)} {quote.from_asset}'
    got = f'{format_amount(quote.to_amount)} {quote.to_asset}'
    fee = f'{format_amount(quote.fee_amount)} {quote.from_asset}'
    if quote.kind == 'buy':
        return f'Buy {got} with {paid}, including a {fee} fee.'
    if quote.kind == 'sell':
        return f'Sell {paid} for {got}, including a {fee} fee.'
    return f'Swap {paid} to {got}, including a {fee} fee.'


def _draft_reply(user, action, quote, summary, transcript):
    draft = drafts.create_draft(user, action, quote, summary, transcript)
    return Reply('draft', f'{summary} Tap approve to confirm.', draft=draft)


def draft_manual_trade(user, kind, from_asset, to_asset, amount, amount_asset=None):
    """A trade from the Trade page. It gets the same locked price and approval step as a voice request."""
    quote = services.quote_trade(kind, from_asset, to_asset, amount, amount_asset)
    if not services.has_balance(user, quote.from_asset, quote.from_amount):
        have = services.balance_of(user, quote.from_asset)
        raise WalletError(
            'insufficient_funds',
            f'You need {format_amount(quote.from_amount)} {quote.from_asset} but only have {format_amount(have)}.',
        )
    return drafts.create_draft(user, kind, quote, _trade_summary(quote), '')


def _handle_trade(user, intent, transcript):
    verb = intent.action
    if not intent.from_asset or not intent.to_asset:
        if verb == 'swap':
            return _question('Which two coins would you like to swap?')
        return _question(f'Which coin would you like to {verb}?')

    amount, amount_asset = _parse_amount(intent, intent.from_asset, user)
    if amount is None:
        return _question(f'How much would you like to {verb}?')

    quote = services.quote_trade(verb, intent.from_asset, intent.to_asset, amount, amount_asset)
    if not services.has_balance(user, quote.from_asset, quote.from_amount):
        return _not_enough(user, quote.from_asset, quote.from_amount)
    return _draft_reply(user, verb, quote, _trade_summary(quote), transcript)


def _resolve_recipient(user, spoken_name):
    """Match a spoken name to a user. Returns (username, reply); reply is set if we need to stop and ask."""
    name = spoken_name.strip().lstrip('@')
    exact = User.objects.filter(username__iexact=name).first()
    if exact:
        return exact.username, None

    matches = list(User.objects.filter(full_name__icontains=name).exclude(pk=user.pk)[:4])
    if not matches:
        return None, Reply('refused', f"I can't find a Vira user called {name}.")
    if len(matches) > 1:
        options = ' or '.join(f'{match.full_name} ({match.username})' for match in matches)
        return None, _question(f'Which {name} do you mean: {options}?')
    return matches[0].username, None


def _handle_send(user, intent, transcript):
    if not intent.asset:
        return _question('Which asset would you like to send?')
    if not intent.recipient and not intent.address:
        return _question('Who would you like to send it to?')

    amount, _ = _parse_amount(intent, intent.asset, user)
    if amount is None:
        return _question(f'How much {intent.asset} would you like to send?')

    username = ''
    if intent.recipient:
        username, stop = _resolve_recipient(user, intent.recipient)
        if stop:
            return stop

    quote = services.quote_send(user, intent.asset, amount, recipient=username, address=intent.address or '')
    if not services.has_balance(user, quote.asset, quote.total):
        return _not_enough(user, quote.asset, quote.total)

    sent = f'{format_amount(quote.amount)} {quote.asset}'
    if quote.recipient:
        summary = f'Send {sent} to {quote.recipient.full_name}, username {quote.recipient.username}.'
    else:
        fee = f'{format_amount(quote.fee_amount)} {quote.asset}'
        summary = f'Send {sent} to the address ending in {quote.address[-4:]}, plus a {fee} network fee.'
    return _draft_reply(user, 'send', quote, summary, transcript)


def _handle_price(intent):
    if not intent.asset:
        return _question('Which coin do you want the price of?')
    if intent.asset == 'NGN':
        rate = simulator.rate('USDT', 'NGN')
        return _answer(f'One USDT is about {rate.quantize(Decimal(1)):,f} naira.')
    asset = simulator.ASSETS.get(intent.asset)
    if asset is None:
        return Reply('refused', f"Vira doesn't support {intent.asset}.")

    row = price_row(asset, simulator.current_time())
    change = Decimal(row['change_24h_pct'])
    direction = 'up' if change >= 0 else 'down'
    ngn = Decimal(row['price_ngn']).quantize(Decimal(1))
    return _answer(
        f"{asset.name} is at {Decimal(row['price_usd']):,f} dollars, about {ngn:,f} naira, "
        f'{direction} {abs(change):f} percent in the last 24 hours.',
        data=row,
    )


def _handle_balance(user, intent):
    if not intent.asset:
        return _handle_portfolio(user)
    if intent.asset not in simulator.ASSETS:
        return Reply('refused', f"Vira doesn't support {intent.asset}.")
    row = next((row for row in services.portfolio(user)['wallets'] if row['asset'] == intent.asset), None)
    if row is None or Decimal(row['balance']) == 0:
        return _answer(f"You don't have any {intent.asset}.")
    amount = format_amount(Decimal(row['balance']))
    if intent.asset == 'NGN':
        return _answer(f'You have {amount} naira.', data=row)
    return _answer(f"You have {amount} {intent.asset}, worth about {Decimal(row['value_usd']):,f} dollars.", data=row)


def _handle_portfolio(user):
    portfolio = services.portfolio(user)
    usd = Decimal(portfolio['total_usd'])
    ngn = Decimal(portfolio['total_ngn']).quantize(Decimal(1))
    return _answer(f'Your portfolio is worth about {usd:,f} dollars, or {ngn:,f} naira.', data=portfolio)


def _handle_history(user, intent):
    transactions = user.transactions.select_related('counterparty')
    if intent.asset:
        transactions = transactions.filter(Q(from_asset=intent.asset) | Q(to_asset=intent.asset))
    period = ''
    if intent.history_days_ago is not None and intent.history_days_ago >= 0:
        zone = ZoneInfo(settings.VIRA_TIME_ZONE)
        day = timezone.now().astimezone(zone).date() - timedelta(days=intent.history_days_ago)
        start = datetime.combine(day, time.min, tzinfo=zone)
        transactions = transactions.filter(created_at__gte=start, created_at__lt=start + timedelta(days=1))
        period = {0: ' today', 1: ' yesterday'}.get(intent.history_days_ago, f' {intent.history_days_ago} days ago')

    rows = TransactionSerializer(transactions[:SPOKEN_HISTORY_LIMIT], many=True).data
    if not rows:
        return _answer(f"You don't have any transactions{period}.", data=[])
    return _answer(' '.join(f"{row['summary']}." for row in rows), data=rows)


def _handle_cancel(user):
    if drafts.cancel_open_draft(user):
        return _answer('Okay, I cancelled that request.')
    return _answer("There's nothing to cancel.")


def _handle_voice_approval(user):
    open_draft = Draft.objects.filter(user=user, status=Draft.Status.PENDING).first()
    if open_draft is None or open_draft.is_expired:
        return _answer("There's nothing waiting for your approval.")
    return _answer("To keep your funds safe, I can't approve by voice. Please tap approve on the screen.")


def _dispatch(user, intent, transcript):
    action = intent.action
    if action in ('buy', 'sell', 'swap'):
        return _handle_trade(user, intent, transcript)
    if action == 'send':
        return _handle_send(user, intent, transcript)
    if action == 'get_price':
        return _handle_price(intent)
    if action == 'get_balance':
        return _handle_balance(user, intent)
    if action == 'get_portfolio':
        return _handle_portfolio(user)
    if action == 'get_history':
        return _handle_history(user, intent)
    if action == 'cancel':
        return _handle_cancel(user)
    if action == 'voice_approval':
        return _handle_voice_approval(user)
    if action == 'clarify':
        return _question(intent.message or 'Could you say that again with a bit more detail?')
    return Reply('refused', intent.message or 'I can help you buy, sell, swap, send and check prices or balances.')


def handle_command(user, text):
    intent = parse_intent(text, _follow_up_history(user))
    try:
        reply = _dispatch(user, intent, text)
    except WalletError as exc:
        reply = Reply('refused', exc.message)
    Turn.objects.create(user=user, text=text, reply=reply.text, needs_follow_up=reply.follow_up)
    return reply, intent
