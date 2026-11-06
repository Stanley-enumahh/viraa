"""
Simulated crypto networks. Nothing touches a real blockchain: a network sets the
fee on a send and is recorded on the transaction. The fees are made up.
"""

import re
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Network:
    code: str
    name: str
    fee_usd: Decimal


TRC20 = Network('TRC20', 'TRON', Decimal('1'))
BEP20 = Network('BEP20', 'BNB Chain', Decimal('0.30'))
ERC20 = Network('ERC20', 'Ethereum', Decimal('5'))
BITCOIN = Network('BTC', 'Bitcoin', Decimal('2'))
SOLANA = Network('SOL', 'Solana', Decimal('0.05'))
XRP_LEDGER = Network('XRP', 'XRP Ledger', Decimal('0.05'))
CARDANO = Network('ADA', 'Cardano', Decimal('0.20'))
DOGECOIN = Network('DOGE', 'Dogecoin', Decimal('0.50'))

ASSET_NETWORKS = {
    'USDT': [TRC20, BEP20, ERC20],
    'BTC': [BITCOIN],
    'ETH': [ERC20],
    'SOL': [SOLANA],
    'BNB': [BEP20],
    'XRP': [XRP_LEDGER],
    'ADA': [CARDANO],
    'DOGE': [DOGECOIN],
}

_NETWORKS_BY_CODE = {network.code: network for networks in ASSET_NETWORKS.values() for network in networks}

_SPOKEN_NAMES = {
    'tron': 'TRC20', 'trc20': 'TRC20', 'trc': 'TRC20',
    'bnb': 'BEP20', 'bnbchain': 'BEP20', 'bnbsmartchain': 'BEP20', 'bsc': 'BEP20',
    'bep20': 'BEP20', 'bep': 'BEP20', 'binance': 'BEP20', 'binancesmartchain': 'BEP20',
    'ethereum': 'ERC20', 'eth': 'ERC20', 'ether': 'ERC20', 'erc20': 'ERC20', 'erc': 'ERC20',
    'bitcoin': 'BTC', 'btc': 'BTC',
    'solana': 'SOL', 'sol': 'SOL',
    'xrp': 'XRP', 'ripple': 'XRP', 'xrpledger': 'XRP',
    'cardano': 'ADA', 'ada': 'ADA',
    'dogecoin': 'DOGE', 'doge': 'DOGE',
}


def normalize_network(value):
    """Turn "TRC-20", "tron" or "BNB Chain" into a network code. Unknown names pass through to be refused."""
    if not value:
        return ''
    cleaned = re.sub(r'[^a-z0-9]', '', value.lower()).removesuffix('network')
    return _SPOKEN_NAMES.get(cleaned, value.strip().upper())


def network_name(code):
    network = _NETWORKS_BY_CODE.get(code)
    return network.name if network else code


def spoken_list(networks):
    names = [network.name for network in networks]
    return ' or '.join(names) if len(names) < 3 else f"{', '.join(names[:-1])} or {names[-1]}"
