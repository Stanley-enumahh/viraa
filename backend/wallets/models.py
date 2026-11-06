import uuid

from django.conf import settings
from django.db import models


class Wallet(models.Model):
    """One simulated balance per user per asset."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wallets')
    asset = models.CharField(max_length=10)
    balance = models.DecimalField(max_digits=24, decimal_places=8, default=0)

    class Meta:
        ordering = ['id']
        constraints = [
            models.UniqueConstraint(fields=['user', 'asset'], name='unique_wallet_per_asset'),
            models.CheckConstraint(condition=models.Q(balance__gte=0), name='wallet_balance_not_negative'),
        ]

    def __str__(self):
        return f'{self.user} {self.asset}: {self.balance}'


class Transaction(models.Model):
    """A completed movement of funds, from the point of view of `user`."""

    class Kind(models.TextChoices):
        BUY = 'buy', 'Buy'
        SELL = 'sell', 'Sell'
        SWAP = 'swap', 'Swap'
        SEND = 'send', 'Send'
        RECEIVE = 'receive', 'Receive'

    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='transactions')
    kind = models.CharField(max_length=10, choices=Kind.choices)

    from_asset = models.CharField(max_length=10, blank=True)
    from_amount = models.DecimalField(max_digits=24, decimal_places=8, null=True, blank=True)
    to_asset = models.CharField(max_length=10, blank=True)
    to_amount = models.DecimalField(max_digits=24, decimal_places=8, null=True, blank=True)
    rate = models.DecimalField(max_digits=30, decimal_places=18, null=True, blank=True)
    fee_amount = models.DecimalField(max_digits=24, decimal_places=8, default=0)

    counterparty = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    address = models.CharField(max_length=64, blank=True)
    network = models.CharField(max_length=10, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f'{self.user} {self.kind} {self.reference}'
