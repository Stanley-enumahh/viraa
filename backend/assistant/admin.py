from django.contrib import admin

from .models import Draft, Turn


@admin.register(Draft)
class DraftAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'user', 'action', 'status', 'summary']
    list_filter = ['status', 'action']


@admin.register(Turn)
class TurnAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'user', 'text', 'reply']
