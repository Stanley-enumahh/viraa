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


class CustomerTests(APITestCase):
    def setUp(self):
        self.ada = User.objects.create_user(username='ada', email='ada@example.com', password='x', full_name='Ada Obi')
        self.tunde = User.objects.create_user(
            username='tunde', email='tunde@example.com', password='x', full_name='Tunde Bello',
        )
        self.client.force_authenticate(self.ada)

    def add(self, username):
        return self.client.post(reverse('customer-list'), {'username': username})

    def test_requires_auth(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(reverse('customer-list')).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_lookup_shows_who_it_is_without_saving_or_exposing_email(self):
        response = self.client.get(reverse('customer-lookup'), {'username': '@TUNDE'})
        self.assertEqual(response.data, {'username': 'tunde', 'full_name': 'Tunde Bello'})
        self.assertFalse(self.ada.customers.exists())

    def test_add_list_and_remove(self):
        added = self.add('Tunde')
        self.assertEqual(added.status_code, status.HTTP_201_CREATED)
        self.assertEqual(added.data['full_name'], 'Tunde Bello')
        self.assertNotIn('email', added.data)

        self.assertEqual([row['username'] for row in self.client.get(reverse('customer-list')).data], ['tunde'])

        removed = self.client.delete(reverse('customer-detail', args=[added.data['id']]))
        self.assertEqual(removed.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(self.ada.customers.exists())
        self.assertTrue(User.objects.filter(username='tunde').exists())

    def test_refusals(self):
        cases = [('nobody', 'unknown_user'), ('ada', 'invalid_customer')]
        for username, code in cases:
            with self.subTest(username=username):
                response = self.add(username)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(response.data['code'], code)
        self.assertIn('sign up', self.add('nobody').data['detail'])

    def test_adding_twice_is_refused(self):
        self.add('tunde')
        response = self.add('tunde')
        self.assertEqual(response.data['code'], 'already_customer')
        self.assertEqual(self.ada.customers.count(), 1)

    def test_each_user_only_sees_and_removes_their_own(self):
        customer_id = self.add('tunde').data['id']
        self.client.force_authenticate(self.tunde)
        self.assertEqual(self.client.get(reverse('customer-list')).data, [])
        response = self.client.delete(reverse('customer-detail', args=[customer_id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.ada.customers.count(), 1)


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
