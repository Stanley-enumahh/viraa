import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Turn(models.Model):
    """One thing the user said and what Vira replied, kept so follow-ups have context."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='assistant_turns')
    text = models.TextField()
    reply = models.TextField()
    needs_follow_up = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']


class Draft(models.Model):
    """A request waiting for the user's click. Holds the exact quote they were shown."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        EXECUTED = 'executed', 'Executed'
        REJECTED = 'rejected', 'Rejected'
        EXPIRED = 'expired', 'Expired'
        FAILED = 'failed', 'Failed'

    class Action(models.TextChoices):
        BUY = 'buy', 'Buy'
        SELL = 'sell', 'Sell'
        SWAP = 'swap', 'Swap'
        SEND = 'send', 'Send'

    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='assistant_drafts')
    action = models.CharField(max_length=10, choices=Action.choices)
    quote = models.JSONField()
    summary = models.TextField()
    transcript = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    transaction = models.ForeignKey(
        'wallets.Transaction', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at', '-id']

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at
