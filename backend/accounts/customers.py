from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from wallets.services import WalletError

from .models import Customer

User = get_user_model()


def find_user(owner, username):
    """The Vira user behind a username, checked so they can be saved as a customer."""
    username = (username or '').strip().lstrip('@')
    user = User.objects.filter(username__iexact=username).first()
    if user is None:
        raise WalletError(
            'unknown_user', f"I can't find a Vira user called {username or 'that'}. They need to sign up first.",
        )
    if user.pk == owner.pk:
        raise WalletError('invalid_customer', "You can't add yourself as a customer.")
    return user


def add_customer(owner, username):
    user = find_user(owner, username)
    try:
        with transaction.atomic():
            return Customer.objects.create(owner=owner, user=user)
    except IntegrityError as exc:
        raise WalletError('already_customer', f'{user.full_name} is already one of your customers.') from exc
