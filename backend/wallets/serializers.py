from decimal import Decimal

from rest_framework import serializers

from .models import Transaction
from .services import format_amount

# 18 digits caps amounts at 10 billion, which keeps conversions inside Decimal's precision.
AMOUNT_FIELD_ARGS = {'max_digits': 18, 'decimal_places': 8, 'min_value': Decimal('0.00000001')}


class TradeRequestSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=['buy', 'sell', 'swap'])
    from_asset = serializers.CharField(max_length=10)
    to_asset = serializers.CharField(max_length=10)
    amount = serializers.DecimalField(**AMOUNT_FIELD_ARGS)
    amount_asset = serializers.CharField(max_length=10, required=False, allow_blank=True)


class SendRequestSerializer(serializers.Serializer):
    asset = serializers.CharField(max_length=10)
    amount = serializers.DecimalField(**AMOUNT_FIELD_ARGS)
    recipient = serializers.CharField(max_length=151, required=False, allow_blank=True)
    address = serializers.CharField(max_length=64, required=False, allow_blank=True)


class TransactionSerializer(serializers.ModelSerializer):
    counterparty = serializers.CharField(source='counterparty.username', default=None, read_only=True)
    summary = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = [
            'reference', 'kind', 'summary', 'from_asset', 'from_amount', 'to_asset', 'to_amount',
            'rate', 'fee_amount', 'counterparty', 'address', 'created_at',
        ]
        read_only_fields = fields

    def get_summary(self, tx):
        paid = f'{format_amount(tx.from_amount)} {tx.from_asset}' if tx.from_amount is not None else ''
        got = f'{format_amount(tx.to_amount)} {tx.to_asset}' if tx.to_amount is not None else ''
        party = f'@{tx.counterparty.username}' if tx.counterparty else (tx.address or 'a former user')
        return {
            Transaction.Kind.BUY: f'Bought {got} with {paid}',
            Transaction.Kind.SELL: f'Sold {paid} for {got}',
            Transaction.Kind.SWAP: f'Swapped {paid} to {got}',
            Transaction.Kind.SEND: f'Sent {paid} to {party}',
            Transaction.Kind.RECEIVE: f'Received {got} from {party}',
        }[tx.kind]
