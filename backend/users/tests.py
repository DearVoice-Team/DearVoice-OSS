from unittest import mock

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from common.factories import DEFAULT_PASSWORD, make_user

User = get_user_model()


class SignupTest(APITestCase):
    url = reverse("signup")

    def test_signup_creates_user_with_hashed_password(self):
        res = self.client.post(self.url, {
            "user_id": "newbie",
            "email": "newbie@example.com",
            "password": DEFAULT_PASSWORD,
            "nickname": "뉴비",
        })

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(user_id="newbie")
        self.assertEqual(user.nickname, "뉴비")
        self.assertTrue(user.is_new_user)
        self.assertFalse(user.is_social_login)
        self.assertNotEqual(user.password, DEFAULT_PASSWORD)
        self.assertTrue(user.check_password(DEFAULT_PASSWORD))

    def test_password_is_not_returned(self):
        res = self.client.post(self.url, {
            "user_id": "newbie", "email": "newbie@example.com", "password": DEFAULT_PASSWORD,
        })
        self.assertNotIn("password", res.json())

    def test_duplicate_user_id_is_rejected(self):
        make_user("alice")
        res = self.client.post(self.url, {
            "user_id": "alice", "email": "other@example.com", "password": DEFAULT_PASSWORD,
        })
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("user_id", res.json())

    def test_duplicate_email_is_rejected(self):
        make_user("alice", email="alice@example.com")
        res = self.client.post(self.url, {
            "user_id": "alice2", "email": "alice@example.com", "password": DEFAULT_PASSWORD,
        })
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", res.json())

    def test_missing_required_fields(self):
        res = self.client.post(self.url, {"user_id": "nopass"})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", res.json())
        self.assertIn("password", res.json())


class CheckAvailabilityTest(APITestCase):
    def setUp(self):
        make_user("alice", email="alice@example.com")

    def test_user_id_taken(self):
        res = self.client.get(reverse("check_user_id"), {"user_id": "alice"})
        self.assertEqual(res.json(), {"available": False})

    def test_user_id_available(self):
        res = self.client.get(reverse("check_user_id"), {"user_id": "bob"})
        self.assertEqual(res.json(), {"available": True})

    def test_user_id_missing_param(self):
        res = self.client.get(reverse("check_user_id"))
        self.assertEqual(res.status_code, 400)

    def test_email_taken(self):
        res = self.client.get(reverse("check_email"), {"email": "alice@example.com"})
        self.assertEqual(res.json(), {"available": False})

    def test_email_available(self):
        res = self.client.get(reverse("check_email"), {"email": "bob@example.com"})
        self.assertEqual(res.json(), {"available": True})

    def test_email_missing_param(self):
        res = self.client.get(reverse("check_email"))
        self.assertEqual(res.status_code, 400)


class LoginTest(APITestCase):
    def setUp(self):
        self.user = make_user("alice")

    def test_login_returns_jwt_pair(self):
        res = self.client.post(reverse("token_obtain_pair"), {
            "user_id": "alice", "password": DEFAULT_PASSWORD,
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("access", res.json())
        self.assertIn("refresh", res.json())

    def test_login_wrong_password(self):
        res = self.client.post(reverse("token_obtain_pair"), {
            "user_id": "alice", "password": "wrong-password",
        })
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_inactive_user_cannot_login(self):
        self.user.is_active = False
        self.user.save()
        res = self.client.post(reverse("token_obtain_pair"), {
            "user_id": "alice", "password": DEFAULT_PASSWORD,
        })
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_issues_new_access_token(self):
        tokens = self.client.post(reverse("token_obtain_pair"), {
            "user_id": "alice", "password": DEFAULT_PASSWORD,
        }).json()
        res = self.client.post(reverse("token_refresh"), {"refresh": tokens["refresh"]})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("access", res.json())


class MeViewTest(APITestCase):
    url = reverse("me_view")

    def test_requires_authentication(self):
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_returns_current_user_with_jwt(self):
        make_user("alice", nickname="앨리스")
        access = self.client.post(reverse("token_obtain_pair"), {
            "user_id": "alice", "password": DEFAULT_PASSWORD,
        }).json()["access"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        res = self.client.get(self.url)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["user_id"], "alice")
        self.assertEqual(res.json()["nickname"], "앨리스")
        self.assertNotIn("password", res.json())


@mock.patch("users.views.google_id_token.verify_oauth2_token")
class GoogleLoginTest(APITestCase):
    url = reverse("google_login")
    idinfo = {"email": "gildong@gmail.com", "sub": "1234567890", "name": "홍길동"}

    def test_missing_id_token(self, mock_verify):
        res = self.client.post(self.url, {})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        mock_verify.assert_not_called()

    def test_invalid_token(self, mock_verify):
        mock_verify.side_effect = ValueError("Wrong audience")
        res = self.client.post(self.url, {"id_token": "bad"})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.exists())

    def test_first_login_creates_social_user(self, mock_verify):
        mock_verify.return_value = self.idinfo
        res = self.client.post(self.url, {"id_token": "valid"})

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        body = res.json()
        self.assertTrue(body["is_new_user"])
        self.assertIn("access", body)
        user = User.objects.get(email="gildong@gmail.com")
        self.assertEqual(user.user_id, "google_1234567890")
        self.assertEqual(user.nickname, "홍길동")
        self.assertTrue(user.is_social_login)
        self.assertFalse(user.has_usable_password())

    def test_second_login_reuses_user(self, mock_verify):
        mock_verify.return_value = self.idinfo
        self.client.post(self.url, {"id_token": "valid"})
        res = self.client.post(self.url, {"id_token": "valid"})

        self.assertFalse(res.json()["is_new_user"])
        self.assertEqual(User.objects.count(), 1)
        self.assertFalse(User.objects.get().is_new_user)

    def test_nickname_defaults_to_email_prefix(self, mock_verify):
        mock_verify.return_value = {"email": "noname@gmail.com", "sub": "42"}
        res = self.client.post(self.url, {"id_token": "valid"})
        self.assertEqual(res.json()["user"]["nickname"], "noname")

    def test_profile_without_email_is_rejected(self, mock_verify):
        mock_verify.return_value = {"sub": "42"}
        res = self.client.post(self.url, {"id_token": "valid"})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
