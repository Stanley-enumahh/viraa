from django.conf import settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()

PASSWORD = 'correct-horse-battery'


def payload(**overrides):
    return {
        'email': 'tunde@example.com',
        'username': 'tunde',
        'full_name': 'Tunde Bello',
        'password': PASSWORD,
        **overrides,
    }


class RegisterTests(APITestCase):
    def test_register_returns_tokens_and_funds_wallets(self):
        response = self.client.post(reverse('register'), payload())

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertNotIn('password', response.data['user'])
        user = User.objects.get(email='tunde@example.com')
        self.assertEqual(
            {wallet.asset: wallet.balance for wallet in user.wallets.all()},
            settings.STARTING_BALANCES,
        )

    def test_duplicate_email_rejected_case_insensitively(self):
        self.client.post(reverse('register'), payload())
        response = self.client.post(reverse('register'), payload(email='TUNDE@example.com', username='other'))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)

    def test_duplicate_username_rejected_case_insensitively(self):
        self.client.post(reverse('register'), payload())
        response = self.client.post(reverse('register'), payload(email='new@example.com', username='TUNDE'))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('username', response.data)

    def test_weak_password_rejected(self):
        response = self.client.post(reverse('register'), payload(password='12345'))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.data)
        self.assertFalse(User.objects.exists())

    def test_bad_username_rejected(self):
        response = self.client.post(reverse('register'), payload(username='has spaces'))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('username', response.data)


class LoginTests(APITestCase):
    def setUp(self):
        self.client.post(reverse('register'), payload())

    def test_login_is_case_insensitive_and_returns_user(self):
        response = self.client.post(reverse('login'), {'email': 'Tunde@Example.com', 'password': PASSWORD})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['user']['username'], 'tunde')

    def test_wrong_password_rejected(self):
        response = self.client.post(reverse('login'), {'email': 'tunde@example.com', 'password': 'nope'})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_token_gives_working_access_token(self):
        login = self.client.post(reverse('login'), {'email': 'tunde@example.com', 'password': PASSWORD})
        refreshed = self.client.post(reverse('token-refresh'), {'refresh': login.data['refresh']})
        self.assertEqual(refreshed.status_code, status.HTTP_200_OK)

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refreshed.data['access']}")
        me = self.client.get(reverse('me'))
        self.assertEqual(me.status_code, status.HTTP_200_OK)
        self.assertEqual(me.data['email'], 'tunde@example.com')

    def test_me_requires_auth(self):
        response = self.client.get(reverse('me'))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
