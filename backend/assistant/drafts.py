"""
Approving a draft is the only way a voice command can move funds.

Claude and the speech services never reach this code. It runs only when the
logged-in owner calls the approve endpoint, and it executes the stored quote, so
they get exactly the amounts they were shown.
"""

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from wallets import services
from wallets.services import SendQuote, TradeQuote, WalletError

from .models import Draft

User = get_user_model()


def create_draft(user, action, quote, summary, transcript):
    """Save a quote for approval. A new draft replaces any the user left open."""
    with transaction.atomic():
        now = timezone.now()
        Draft.objects.filter(user=user, status=Draft.Status.PENDING).update(
            status=Draft.Status.REJECTED, resolved_at=now,
        )
        return Draft.objects.create(
            user=user,
            action=action,
            quote=quote.as_dict(),
            summary=summary,
            transcript=transcript,
            expires_at=now + timedelta(seconds=settings.DRAFT_TTL_SECONDS),
        )


def _execute(draft):
    quote = draft.quote
    if draft.action == Draft.Action.SEND:
        recipient = None
        if quote['recipient']:
            recipient = User.objects.filter(username=quote['recipient']).first()
            if recipient is None:
                raise WalletError('unknown_recipient', 'That recipient no longer exists.')
        return services.execute_send(draft.user, SendQuote(
            asset=quote['asset'],
            amount=Decimal(quote['amount']),
            fee_amount=Decimal(quote['fee_amount']),
            recipient=recipient,
            address=quote['address'] or '',
            network=quote.get('network') or '',
        ))
    return services.execute_trade(draft.user, TradeQuote(
        kind=quote['kind'],
        from_asset=quote['from_asset'],
        from_amount=Decimal(quote['from_amount']),
        to_asset=quote['to_asset'],
        to_amount=Decimal(quote['to_amount']),
        rate=Decimal(quote['rate']),
        fee_amount=Decimal(quote['fee_amount']),
    ))


def approve_draft(user, reference):
    """Execute a pending draft. Approving one that already ran returns it, so a double click is harmless."""
    error = None
    with transaction.atomic():
        draft = Draft.objects.select_for_update().get(user=user, reference=reference)
        if draft.status == Draft.Status.EXECUTED:
            return draft
        if draft.status != Draft.Status.PENDING:
            raise WalletError('draft_closed', f'This request is already {draft.status}.')

        if draft.is_expired:
            draft.status = Draft.Status.EXPIRED
            error = WalletError('draft_expired', 'This request expired. Ask me again for a fresh price.')
        else:
            try:
                with transaction.atomic():
                    draft.transaction = _execute(draft)
                draft.status = Draft.Status.EXECUTED
            except WalletError as exc:
                draft.status = Draft.Status.FAILED
                error = exc
        draft.resolved_at = timezone.now()
        draft.save(update_fields=['status', 'transaction', 'resolved_at'])

    if error:
        raise error
    return draft


def reject_draft(user, reference):
    with transaction.atomic():
        draft = Draft.objects.select_for_update().get(user=user, reference=reference)
        if draft.status == Draft.Status.REJECTED:
            return draft
        if draft.status != Draft.Status.PENDING:
            raise WalletError('draft_closed', f'This request is already {draft.status}.')
        draft.status = Draft.Status.REJECTED
        draft.resolved_at = timezone.now()
        draft.save(update_fields=['status', 'resolved_at'])
    return draft


def cancel_open_draft(user):
    """Cancel by voice. Returns how many were cancelled. Saying yes can never approve one."""
    return Draft.objects.filter(user=user, status=Draft.Status.PENDING).update(
        status=Draft.Status.REJECTED, resolved_at=timezone.now(),
    )
