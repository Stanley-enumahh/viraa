from django.contrib.auth.models import AbstractUser, UserManager as DjangoUserManager
from django.db import models
from django.db.models.functions import Lower


class UserManager(DjangoUserManager):
    """Lets `createsuperuser` and friends work with email as the login field."""

    def create_user(self, username, email=None, password=None, **extra_fields):
        return super().create_user(username, (email or '').lower(), password, **extra_fields)

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        return super().create_superuser(username, (email or '').lower(), password, **extra_fields)


class User(AbstractUser):
    """Logs in with email. `username` is the handle people say out loud: "send 50 USDT to tunde"."""

    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=120)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'full_name']

    objects = UserManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower('username'), name='unique_username_ci'),
        ]

    def __str__(self):
        return self.username


class Customer(models.Model):
    """Someone a user has saved so they can pay them by name. They must have a Vira account."""

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='customers')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='+')
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['user__full_name', 'id']
        constraints = [
            models.UniqueConstraint(fields=['owner', 'user'], name='unique_customer_per_owner'),
        ]

    def __str__(self):
        return f'{self.owner} -> {self.user}'
