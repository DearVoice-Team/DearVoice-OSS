from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from common.factories import DEFAULT_PASSWORD, bucket_url, make_user
from letters.models import Letter, LetterRecipient
from skyvoice.models import SkyVoiceLetter


def make_letter(sender, title, recipient_email=None, recipient_user=None):
    letter = Letter.objects.create(sender=sender, audio_url=bucket_url("a.webm"), title=title)
    LetterRecipient.objects.create(letter=letter, email=recipient_email, user=recipient_user)
    return letter


def make_sky_letter(user, title):
    return SkyVoiceLetter.objects.create(
        user=user, title=title, receiver_name="할머니", receiver_gender="여",
        receiver_age=80, receiver_type="할머니", content_text="보고 싶어요",
    )


class MypageAuthTest(APITestCase):
    def test_all_endpoints_require_authentication(self):
        urls = [
            ("get", reverse("sent-letters")),
            ("get", reverse("received-letters")),
            ("patch", reverse("letter-mark-read", args=["00000000-0000-0000-0000-000000000000"])),
            ("delete", reverse("delete-account")),
            ("delete", reverse("delete-sent-letter", args=["letter", "00000000-0000-0000-0000-000000000000"])),
        ]
        for method, url in urls:
            with self.subTest(url=url):
                res = getattr(self.client, method)(url)
                self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class LetterBoxTest(APITestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.letter = make_letter(self.alice, "alice→bob", recipient_email=self.bob.email)
        self.sky = make_sky_letter(self.alice, "alice→하늘")
        make_letter(self.bob, "bob→carol", recipient_email="carol@example.com")

    def test_sent_box_merges_letters_and_sky_letters(self):
        self.client.force_authenticate(self.alice)
        res = self.client.get(reverse("sent-letters"))

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        items = {(i["type"], i["title"]) for i in res.json()}
        self.assertEqual(items, {("letter", "alice→bob"), ("sky", "alice→하늘")})

    def test_sent_box_is_sorted_newest_first(self):
        Letter.objects.filter(pk=self.letter.pk).update(created_at=timezone.now() - timedelta(days=1))
        self.client.force_authenticate(self.alice)
        res = self.client.get(reverse("sent-letters"))
        self.assertEqual([i["title"] for i in res.json()], ["alice→하늘", "alice→bob"])

    def test_received_box_contains_letters_sent_to_me(self):
        self.client.force_authenticate(self.bob)
        res = self.client.get(reverse("received-letters"))

        items = [(i["type"], i["title"]) for i in res.json()]
        self.assertEqual(items, [("letter", "alice→bob")])
        self.assertEqual(res.json()[0]["sender_display_id"], "alice")

    def test_received_box_contains_my_sky_letter_replies(self):
        self.client.force_authenticate(self.alice)
        res = self.client.get(reverse("received-letters"))
        self.assertEqual([i["type"] for i in res.json()], ["sky"])


class MarkAsReadTest(APITestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.letter = make_letter(self.alice, "hi", recipient_email=self.bob.email)
        self.url = reverse("letter-mark-read", args=[self.letter.id])

    def test_recipient_marks_letter_as_read(self):
        self.client.force_authenticate(self.bob)
        res = self.client.patch(self.url)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(LetterRecipient.objects.get().is_read)

    def test_marking_twice_is_ok(self):
        self.client.force_authenticate(self.bob)
        self.client.patch(self.url)
        res = self.client.patch(self.url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_non_recipient_gets_404(self):
        self.client.force_authenticate(make_user("mallory"))
        res = self.client.patch(self.url)
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(LetterRecipient.objects.get().is_read)


class DeleteSentLetterTest(APITestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.letter = make_letter(self.alice, "hi", recipient_email="bob@example.com")
        self.sky = make_sky_letter(self.alice, "sky")

    def url(self, letter_type, letter_id):
        return reverse("delete-sent-letter", args=[letter_type, letter_id])

    def test_delete_own_letter(self):
        self.client.force_authenticate(self.alice)
        res = self.client.delete(self.url("letter", self.letter.id))
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Letter.objects.exists())

    def test_cannot_delete_others_letter(self):
        self.client.force_authenticate(make_user("mallory"))
        res = self.client.delete(self.url("letter", self.letter.id))
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Letter.objects.exists())

    def test_invalid_type(self):
        self.client.force_authenticate(self.alice)
        res = self.client.delete(self.url("unknown", self.letter.id))
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)


class DeleteAccountTest(APITestCase):
    url = reverse("delete-account")

    def setUp(self):
        self.alice = make_user("alice")
        self.client.force_authenticate(self.alice)

    def test_password_required(self):
        res = self.client.delete(self.url, {}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_wrong_password(self):
        res = self.client.delete(self.url, {"password": "wrong"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.alice.refresh_from_db()
        self.assertTrue(self.alice.is_active)

    def test_deactivates_account(self):
        res = self.client.delete(self.url, {"password": DEFAULT_PASSWORD}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.alice.refresh_from_db()
        self.assertFalse(self.alice.is_active)
