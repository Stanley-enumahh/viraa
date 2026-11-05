"""
Rewrites a reply so it sounds right when spoken.

Text-to-speech garbles strings like "0.0001337 BTC" and "252,199.5", and nobody can
follow eight decimals by ear anyway. The approval card always shows the exact
amounts, so speech can round, as long as it says "about" when it does.
"""

import re
from decimal import ROUND_HALF_UP, Decimal

_SPOKEN_ASSETS = {
    'NGN': 'naira',
    'BTC': 'Bitcoin',
    'ETH': 'Ethereum',
    'SOL': 'Solana',
    'ADA': 'Cardano',
    'DOGE': 'Dogecoin',
    'BNB': 'B N B',
    'XRP': 'X R P',
    'USDT': 'U S D T',
}
_ASSET_PATTERN = re.compile(rf"\b({'|'.join(_SPOKEN_ASSETS)})\b")
# Skips digits inside names, and the last digits of an address, which are not an amount.
_NUMBER_PATTERN = re.compile(r'(?<![\w.,])(?<!ending in )\d[\d,]*(?:\.\d+)?(?!\w)')
_DIGIT_WORDS = 'zero one two three four five six seven eight nine'.split()
_SMALL_SIGNIFICANT_DIGITS = 4
_LARGE_SIGNIFICANT_DIGITS = 3


def _spell_decimals(digits):
    return ' '.join(_DIGIT_WORDS[int(digit)] for digit in digits)


def _round_significant(value, digits):
    return value.quantize(Decimal(1).scaleb(value.adjusted() - digits + 1), rounding=ROUND_HALF_UP)


def _speak_number(match):
    value = Decimal(match.group().replace(',', ''))
    if value == 0:
        return 'zero'

    if value < 1:
        rounded = _round_significant(value, _SMALL_SIGNIFICANT_DIGITS)
        decimals = format(rounded.normalize(), 'f').partition('.')[2]
        spoken = f'zero point {_spell_decimals(decimals)}'
    elif value < 1000:
        rounded = value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        whole, _, decimals = format(rounded.normalize(), 'f').partition('.')
        spoken = f'{whole} point {_spell_decimals(decimals)}' if decimals else whole
    else:
        rounded = _round_significant(value, _LARGE_SIGNIFICANT_DIGITS)
        if rounded >= 1000000:
            whole, _, decimals = format((rounded / 1000000).normalize(), 'f').partition('.')
            spoken = f'{whole} point {_spell_decimals(decimals)} million' if decimals else f'{whole} million'
        else:
            spoken = f'{int(rounded):,}'
    return spoken if rounded == value else f'about {spoken}'


def speakable(text):
    text = _NUMBER_PATTERN.sub(_speak_number, text).replace('about about', 'about')
    return _ASSET_PATTERN.sub(lambda match: _SPOKEN_ASSETS[match.group()], text)
