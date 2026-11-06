from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from wallets.services import create_starting_wallets

from .models import Customer

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'full_name', 'date_joined']
        read_only_fields = fields


class CustomerSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    full_name = serializers.CharField(source='user.full_name', read_only=True)

    class Meta:
        model = Customer
        fields = ['id', 'username', 'full_name', 'added_at']
        read_only_fields = fields


class CustomerRequestSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=151)


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    username = serializers.RegexField(r'^[A-Za-z0-9_]{3,30}$', error_messages={
        'invalid': 'Use 3-30 letters, numbers or underscores.',
    })

    class Meta:
        model = User
        fields = ['email', 'username', 'full_name', 'password']

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError('An account with this email already exists.')
        return value

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError('This username is taken.')
        return value

    def validate(self, attrs):
        candidate = User(email=attrs['email'], username=attrs['username'], full_name=attrs['full_name'])
        try:
            validate_password(attrs['password'], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'password': exc.messages})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User.objects.create_user(password=password, **validated_data)
        create_starting_wallets(user)
        return user


class LoginSerializer(TokenObtainPairSerializer):
    """Standard JWT login, but case-insensitive on email and returns the user too."""

    def validate(self, attrs):
        attrs[self.username_field] = attrs[self.username_field].lower()
        data = super().validate(attrs)
        data['user'] = UserSerializer(self.user).data
        return data
