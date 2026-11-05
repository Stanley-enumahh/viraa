"""
Everything that moves simulated funds goes through here.

Each action has two steps: a quote (calculates, changes nothing) and an execute
(applies that quote). Voice drafts store a quote so the user can approve the
exact amounts they were shown.
"""

import re
from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_UP, Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction

from market import simulator

from .models import Transaction, Wallet

User = get_user_model()

TRADE_FEE_RATE = Decimal('0.005')
EXTERNAL_SEND_FEE_USD = Decimal('1')
PAYMENT_ASSETS = {'NGN', 'USDT'}
ADDRESS_PATTERN = re.compile(r'^[A-Za-z0-9]{16,64}$')


class WalletError(Exception):
    """A request we refuse, with a message that is safe to show or speak to the user."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def format_amount(amount):
    if amount == 0:
        return '0'
    return f'{amount.normalize():,f}'


def _places(asset):
    return Decimal('0.01') if asset in PAYMENT_ASSETS else Decimal('0.00000001')


def _round_up(amount, asset):
    return amount.quantize(_places(asset), rounding=ROUND_UP)


def _round_down(amount, asset):
    return amount.quantize(_places(asset), rounding=ROUND_DOWN)


def _clean_asset(symbol):
    symbol = (symbol or '').strip().upper()
    if symbol not in simulator.ASSETS:
        raise WalletError('unknown_asset', f"Vira doesn't support {symbol or 'that asset'}.")
    return symbol


def _check_pair(kind, from_asset, to_asset):
    if from_asset == to_asset:
        raise WalletError('invalid_pair', 'Pick two different assets.')
    from_is_crypto = not simulator.ASSETS[from_asset].is_fiat
    to_is_crypto = not simulator.ASSETS[to_asset].is_fiat
    allowed = {
        Transaction.Kind.BUY: from_asset in PAYMENT_ASSETS and to_is_crypto,
        Transaction.Kind.SELL: from_is_crypto and to_asset in PAYMENT_ASSETS,
        Transaction.Kind.SWAP: from_is_crypto and to_is_crypto,
    }
    if not allowed.get(kind, False):
        raise WalletError('invalid_pair', f"You can't {kind} {from_asset} to {to_asset}.")


@dataclass(frozen=True)
class TradeQuote:
    kind: str
    from_asset: str
    from_amount: Decimal
    to_asset: str
    to_amount: Decimal
    rate: Decimal
    fee_amount: Decimal

    def as_dict(self):
        return {
            'kind': self.kind,
            'from_asset': self.from_asset,
            'from_amount': format(self.from_amount, 'f'),
            'to_asset': self.to_asset,
            'to_amount': format(self.to_amount, 'f'),
            'rate': format(self.rate.quantize(Decimal(1).scaleb(-18)), 'f'),
            'fee_asset': self.from_asset,
            'fee_amount': format(self.fee_amount, 'f'),
        }


def quote_trade(kind, from_asset, to_asset, amount, amount_asset=None, at=None):
    """Price a trade. `amount` is in `amount_asset`, which may be either side.

    The fee comes out of what the user pays, so `from_amount` is the full debit.
    """
    from_asset, to_asset = _clean_asset(from_asset), _clean_asset(to_asset)
    _check_pair(kind, from_asset, to_asset)
    amount_asset = _clean_asset(amount_asset) if amount_asset else from_asset
    if amount_asset not in (from_asset, to_asset):
        raise WalletError('invalid_amount', f'Give the amount in {from_asset} or {to_asset}.')

    rate = simulator.rate(from_asset, to_asset, at)
    if amount_asset == from_asset:
        from_amount = _round_up(amount, from_asset)
        fee_amount = _round_up(from_amount * TRADE_FEE_RATE, from_asset)
        to_amount = _round_down((from_amount - fee_amount) * rate, to_asset)
    else:
        to_amount = _round_down(amount, to_asset)
        from_amount = _round_up(to_amount / rate / (1 - TRADE_FEE_RATE), from_asset)
        fee_amount = _round_up(from_amount * TRADE_FEE_RATE, from_asset)

    if to_amount <= 0 or from_amount <= fee_amount:
        raise WalletError('amount_too_small', 'That amount is too small to trade.')
    return TradeQuote(kind, from_asset, from_amount, to_asset, to_amount, rate, fee_amount)


@dataclass(frozen=True)
class SendQuote:
    asset: str
    amount: Decimal
    fee_amount: Decimal
    recipient: User | None
    address: str

    @property
    def total(self):
        return self.amount + self.fee_amount

    def as_dict(self):
        return {
            'asset': self.asset,
            'amount': format(self.amount, 'f'),
            'fee_amount': format(self.fee_amount, 'f'),
            'total': format(self.total, 'f'),
            'recipient': self.recipient.username if self.recipient else None,
            'recipient_name': self.recipient.full_name if self.recipient else None,
            'address': self.address or None,
        }


def quote_send(sender, asset, amount, recipient='', address='', at=None):
    """Price a send to a Vira username (free) or an external address (flat fee)."""
    asset = _clean_asset(asset)
    recipient = (recipient or '').strip().lstrip('@')
    address = (address or '').strip()
    if bool(recipient) == bool(address):
        raise WalletError('invalid_destination', 'Send to either a Vira username or an external address.')

    amount = _round_down(amount, asset)
    if amount <= 0:
        raise WalletError('amount_too_small', 'That amount is too small to send.')

    if recipient:
        user = User.objects.filter(username__iexact=recipient).first()
        if user is None:
            raise WalletError('unknown_recipient', f"I can't find a Vira user called {recipient}.")
        if user.pk == sender.pk:
            raise WalletError('invalid_destination', "You can't send funds to yourself.")
        return SendQuote(asset, amount, Decimal(0), user, '')

    if simulator.ASSETS[asset].is_fiat:
        raise WalletError('invalid_destination', f'{asset} can only be sent to another Vira user.')
    if not ADDRESS_PATTERN.match(address):
        raise WalletError('invalid_destination', "That doesn't look like a valid address.")
    fee = _round_up(EXTERNAL_SEND_FEE_USD / simulator.price_usd(asset, at), asset)
    return SendQuote(asset, amount, fee, None, address)


def _locked_wallet(user, asset):
    Wallet.objects.get_or_create(user=user, asset=asset)
    return Wallet.objects.select_for_update().get(user=user, asset=asset)


def _debit(user, asset, amount):
    wallet = _locked_wallet(user, asset)
    if wallet.balance < amount:
        raise WalletError(
            'insufficient_funds',
            f'You need {format_amount(amount)} {asset} but only have {format_amount(wallet.balance)}.',
        )
    wallet.balance -= amount
    wallet.save(update_fields=['balance'])


def _credit(user, asset, amount):
    wallet = _locked_wallet(user, asset)
    wallet.balance += amount
    wallet.save(update_fields=['balance'])


@transaction.atomic
def execute_trade(user, quote):
    _debit(user, quote.from_asset, quote.from_amount)
    _credit(user, quote.to_asset, quote.to_amount)
    return Transaction.objects.create(
        user=user,
        kind=quote.kind,
        from_asset=quote.from_asset,
        from_amount=quote.from_amount,
        to_asset=quote.to_asset,
        to_amount=quote.to_amount,
        rate=quote.rate,
        fee_amount=quote.fee_amount,
    )


@transaction.atomic
def execute_send(sender, quote):
    _debit(sender, quote.asset, quote.total)
    if quote.recipient:
        _credit(quote.recipient, quote.asset, quote.amount)
        Transaction.objects.create(
            user=quote.recipient,
            kind=Transaction.Kind.RECEIVE,
            to_asset=quote.asset,
            to_amount=quote.amount,
            counterparty=sender,
        )
    return Transaction.objects.create(
        user=sender,
        kind=Transaction.Kind.SEND,
        from_asset=quote.asset,
        from_amount=quote.amount,
        fee_amount=quote.fee_amount,
        counterparty=quote.recipient,
        address=quote.address,
    )


def has_balance(user, asset, amount):
    wallet = Wallet.objects.filter(user=user, asset=asset).first()
    return wallet is not None and wallet.balance >= amount


def portfolio(user, at=None):
    at = simulator.current_time() if at is None else at
    rows = []
    total_usd = total_ngn = Decimal(0)
    for wallet in user.wallets.all():
        value_usd = (wallet.balance * simulator.price_usd(wallet.asset, at)).quantize(Decimal('0.01'))
        value_ngn = (wallet.balance * simulator.rate(wallet.asset, 'NGN', at)).quantize(Decimal('0.01'))
        total_usd += value_usd
        total_ngn += value_ngn
        rows.append({
            'asset': wallet.asset,
            'name': simulator.ASSETS[wallet.asset].name,
            'balance': format(wallet.balance, 'f'),
            'value_usd': format(value_usd, 'f'),
            'value_ngn': format(value_ngn, 'f'),
        })
    return {'wallets': rows, 'total_usd': format(total_usd, 'f'), 'total_ngn': format(total_ngn, 'f')}


def create_starting_wallets(user):
    """Give a new user their simulated funds."""
    return Wallet.objects.bulk_create(
        Wallet(user=user, asset=asset, balance=balance)
        for asset, balance in settings.STARTING_BALANCES.items()
    )
