"""
Turns what the user said into a structured intent.

Claude does the understanding. The rule-based parser keeps the main commands
working if Claude can't be reached. An intent is only a description of what the
user asked for: numbers, checks and replies all come from our own code.
"""

import json
import logging
import re
from dataclasses import dataclass

import anthropic
from django.conf import settings

logger = logging.getLogger(__name__)

ACTIONS = [
    'buy', 'sell', 'swap', 'send',
    'get_price', 'get_balance', 'get_portfolio', 'get_history',
    'add_customer', 'list_customers',
    'cancel', 'voice_approval', 'clarify', 'unsupported',
]

ASSET_ALIASES = {
    'bitcoin': 'BTC', 'btc': 'BTC',
    'ethereum': 'ETH', 'ether': 'ETH', 'eth': 'ETH',
    'solana': 'SOL', 'sol': 'SOL',
    'bnb': 'BNB', 'binance coin': 'BNB',
    'xrp': 'XRP', 'ripple': 'XRP',
    'cardano': 'ADA', 'ada': 'ADA',
    'dogecoin': 'DOGE', 'doge': 'DOGE',
    'usdt': 'USDT', 'tether': 'USDT', 'dollars': 'USDT', 'dollar': 'USDT',
    'naira': 'NGN', 'ngn': 'NGN',
}


def normalize_asset(value):
    if not value:
        return None
    cleaned = value.strip().lower()
    return ASSET_ALIASES.get(cleaned, cleaned.upper())


@dataclass
class Intent:
    action: str
    source: str
    from_asset: str | None = None
    to_asset: str | None = None
    asset: str | None = None
    amount: str | None = None
    amount_asset: str | None = None
    fraction: float | None = None
    recipient: str | None = None
    address: str | None = None
    network: str | None = None
    history_days_ago: int | None = None
    message: str | None = None


def _nullable(json_type):
    return {'type': [json_type, 'null']}


INTENT_SCHEMA = {
    'type': 'object',
    'properties': {
        'action': {'type': 'string', 'enum': ACTIONS},
        'from_asset': _nullable('string'),
        'to_asset': _nullable('string'),
        'asset': _nullable('string'),
        'amount': _nullable('string'),
        'amount_asset': _nullable('string'),
        'fraction': _nullable('number'),
        'recipient': _nullable('string'),
        'address': _nullable('string'),
        'network': _nullable('string'),
        'history_days_ago': _nullable('integer'),
        'message': _nullable('string'),
    },
    'required': [
        'action', 'from_asset', 'to_asset', 'asset', 'amount', 'amount_asset',
        'fraction', 'recipient', 'address', 'network', 'history_days_ago', 'message',
    ],
    'additionalProperties': False,
}

SYSTEM_PROMPT = """You are the language understanding layer of Vira, a voice assistant for a crypto wallet that uses simulated funds. You receive speech transcripts, which may contain recognition errors, Nigerian English or Pidgin. Work out what the user wants and describe it in the output format. Other software checks balances, prices the request and asks the user to approve it, so never state prices, balances or results yourself.

Assets: BTC, ETH, SOL, BNB, XRP, ADA, DOGE, USDT and NGN (naira). Use these symbols. Treat "dollars" as USDT. Correct obvious mishearings, such as "salana" to SOL.

Actions:
- buy: from_asset is what they pay with (NGN or USDT; use NGN if they don't say), to_asset is the coin.
- sell: from_asset is the coin, to_asset is what they receive (NGN or USDT; use NGN if they don't say).
- swap: from_asset and to_asset are both crypto. "Convert" and "change" between coins mean swap.
- send: asset, amount, and either recipient (the name or username as spoken, without @) or address. Set network to the crypto network if they name one, such as TRON, TRC20, BNB Chain, BEP20, Ethereum or ERC20. Otherwise leave it null, and don't ask for it yourself.
- add_customer: they want to save someone as a customer or contact. recipient is the username as spoken, without @.
- list_customers: they want to hear who their saved customers are.
- get_price: asset is the coin they asked about.
- get_balance: asset is the one balance they asked about.
- get_portfolio: their total or all their balances.
- get_history: optional asset; history_days_ago is 0 for today, 1 for yesterday, otherwise null.
- cancel: they want to cancel or dismiss the request on screen.
- voice_approval: they are trying to confirm a request by voice, such as "yes", "approve it" or "go ahead".
- clarify: required information is missing or the request is ambiguous. Put one short question in message.
- unsupported: anything Vira can't do, including non-wallet topics. Put one short, friendly sentence saying what Vira can help with in message.

Amounts:
- amount is a plain decimal string with no commas or currency symbols: "20k" is "20000", "5 million" is "5000000", "half a million" is "500000".
- amount_asset is the asset the amount is in. "Buy 20k naira of bitcoin" has amount_asset NGN. "Buy 0.01 bitcoin" has amount_asset BTC.
- For a share of a balance use fraction instead of amount: "half" is 0.5, "a quarter" is 0.25, "all" or "everything" is 1.
- A bare number with no asset on a buy, like "buy 5000 of bitcoin", is in the asset they pay with.

The conversation may include earlier turns where you asked a question. Combine them with the latest message to complete the request. If the latest message is a new request, follow it instead. Set every field that doesn't apply to null."""


class IntentUnavailable(Exception):
    pass


_client = None


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(
            api_key=settings.ANTHROPIC_API_KEY,
            timeout=settings.CLAUDE_TIMEOUT_SECONDS,
            max_retries=1,
        )
    return _client


def _parse_with_claude(text, history):
    if not settings.ANTHROPIC_API_KEY:
        raise IntentUnavailable('ANTHROPIC_API_KEY is not set')

    messages = []
    for turn in history:
        messages.append({'role': 'user', 'content': turn.text})
        messages.append({'role': 'assistant', 'content': turn.reply})
    messages.append({'role': 'user', 'content': text})

    try:
        response = _get_client().beta.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=2000,
            betas=['server-side-fallback-2026-07-01'],
            fallbacks='default',
            system=SYSTEM_PROMPT,
            messages=messages,
            output_config={
                'effort': 'low',
                'format': {'type': 'json_schema', 'schema': INTENT_SCHEMA},
            },
        )
    except anthropic.APIError as exc:
        raise IntentUnavailable(f'Claude request failed: {exc}') from exc

    if response.stop_reason != 'end_turn':
        raise IntentUnavailable(f'Claude stopped with {response.stop_reason}')
    try:
        raw = next(block.text for block in response.content if block.type == 'text')
        data = json.loads(raw)
    except (StopIteration, ValueError) as exc:
        raise IntentUnavailable('Claude returned no usable output') from exc

    return Intent(
        action=data['action'],
        source='claude',
        from_asset=normalize_asset(data['from_asset']),
        to_asset=normalize_asset(data['to_asset']),
        asset=normalize_asset(data['asset']),
        amount=data['amount'],
        amount_asset=normalize_asset(data['amount_asset']),
        fraction=data['fraction'],
        recipient=data['recipient'],
        address=data['address'],
        network=data['network'],
        history_days_ago=data['history_days_ago'],
        message=data['message'],
    )


_ASSET_WORDS = '|'.join(sorted(map(re.escape, ASSET_ALIASES), key=len, reverse=True))
_AMOUNT = r'(?P<amount>\d[\d,]*(?:\.\d+)?)\s*(?P<scale>k|m|thousand|million)?\b'
_FRACTIONS = {'half': 0.5, 'quarter': 0.25, 'all': 1.0, 'everything': 1.0}
_SCALES = {'k': 1000, 'thousand': 1000, 'm': 1000000, 'million': 1000000}


def _amount_from(match):
    amount = match.group('amount').replace(',', '')
    scale = match.group('scale')
    if scale:
        whole, _, decimals = amount.partition('.')
        amount = str(int(whole) * _SCALES[scale] + int(float(f'0.{decimals or 0}') * _SCALES[scale]))
    return amount


def _find_assets(text):
    return [ASSET_ALIASES[word] for word in re.findall(rf'\b(?:{_ASSET_WORDS})\b', text)]


def _find_fraction(text):
    for word, value in _FRACTIONS.items():
        if re.search(rf'\b{word}\b', text):
            return value
    return None


def _parse_with_rules(text):
    """Enough to demo the main commands when Claude is down. Anything else asks to rephrase."""
    text = text.lower().strip().rstrip('.?!')
    assets = _find_assets(text)
    amount_match = re.search(_AMOUNT, text)
    amount = _amount_from(amount_match) if amount_match else None
    fraction = _find_fraction(text)
    after_amount = text[amount_match.end():] if amount_match else ''
    next_asset = _find_assets(after_amount)
    amount_asset = next_asset[0] if next_asset and after_amount.strip().startswith(tuple(ASSET_ALIASES)) else None

    def intent(action, **fields):
        return Intent(action=action, source='fallback', **fields)

    if re.search(r'\b(cancel|never mind|nevermind)\b', text):
        return intent('cancel')
    if re.fullmatch(r'(yes|yeah|yep|ok|okay|confirm|approve|approve it|go ahead|do it)', text):
        return intent('voice_approval')

    new_customer = re.search(r'\b(?:add|save)\s+@?(?P<username>[a-z0-9_]+)\b.*\b(?:customers?|contacts?)\b', text)
    if new_customer:
        return intent('add_customer', recipient=new_customer.group('username'))
    if re.search(r'\b(customers|contacts)\b', text):
        return intent('list_customers')

    send = re.search(
        r'\bsend\b.*?\bto\s+@?(?P<recipient>[a-z0-9_]+)(?:\s+(?:on|via|through|using)\s+(?:the\s+)?(?P<network>[a-z0-9 -]+))?\s*$',
        text,
    )
    if send and assets:
        return intent(
            'send', asset=assets[0], amount=amount, fraction=fraction,
            recipient=send.group('recipient'), network=send.group('network'),
        )

    if re.search(r'\b(buy|purchase)\b', text):
        coins = [asset for asset in assets if asset != 'NGN']
        target = coins[-1] if coins else None
        payment = next((asset for asset in assets if asset in ('NGN', 'USDT') and asset != target), 'NGN')
        return intent(
            'buy', from_asset=payment, to_asset=target, amount=amount,
            amount_asset=amount_asset or payment, fraction=fraction,
        )

    if re.search(r'\bsell\b', text):
        coin = next((asset for asset in assets if asset != 'NGN'), None)
        receive = next((asset for asset in assets if asset in ('NGN', 'USDT') and asset != coin), 'NGN')
        return intent(
            'sell', from_asset=coin, to_asset=receive, amount=amount,
            amount_asset=amount_asset or coin, fraction=fraction,
        )

    if re.search(r'\b(swap|convert|change)\b', text) and len(assets) >= 2:
        return intent(
            'swap', from_asset=assets[0], to_asset=assets[1], amount=amount,
            amount_asset=amount_asset or assets[0], fraction=fraction,
        )

    if re.search(r'\b(price|cost|worth|rate)\b', text) and assets:
        return intent('get_price', asset=assets[0])
    if re.search(r'\b(transaction|transactions|history|activity)\b', text):
        return intent('get_history', asset=assets[0] if assets else None)
    if re.search(r'\b(how much|balance|do i have)\b', text):
        if assets:
            return intent('get_balance', asset=assets[0])
        return intent('get_portfolio')
    if re.search(r'\bportfolio\b', text):
        return intent('get_portfolio')

    return intent(
        'unsupported',
        message='Sorry, I didn\'t get that. Try "buy 20k naira of bitcoin" or "what\'s the price of solana".',
    )


def parse_intent(text, history=()):
    try:
        return _parse_with_claude(text, history)
    except IntentUnavailable as exc:
        logger.warning('Using rule-based parser: %s', exc)
        return _parse_with_rules(text)
