from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ['email', 'username', 'full_name', 'is_staff']
    fieldsets = DjangoUserAdmin.fieldsets + (('Vira', {'fields': ['full_name']}),)
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ('Vira', {'fields': ['email', 'full_name']}),
    )
