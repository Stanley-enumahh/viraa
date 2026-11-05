from django.contrib import admin

from .models import Transaction, Wallet


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ['user', 'asset', 'balance']
    list_filter = ['asset']


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'user', 'kind', 'from_amount', 'from_asset', 'to_amount', 'to_asset']
    list_filter = ['kind']
