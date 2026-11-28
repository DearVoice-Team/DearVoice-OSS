"""편지(letters) API / Celery 태스크 테스트.

외부 서비스(S3, CLOVA, SMTP)는 mock 또는 테스트 설정으로 대체한다.
"""
from datetime import timedelta
from unittest import mock
from urllib.parse import urlparse

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from common.factories import bucket_url, make_user
from letters.models import Letter, LetterRecipient
from letters.tasks import send_letter_task, send_scheduled_letters

AUDIO_URL = bucket_url("uploads/sample.webm")


def make_letter(sender, recipients=(), **extra):
    letter = Letter.objects.create(sender=sender, audio_url=AUDIO_URL, transcript="안녕", **extra)
    for r in recipients:
        LetterRecipient.objects.create(letter=letter, **r)
    return letter


class LetterCreateTest(APITestCase):
    url = reverse("letter-create")

    def setUp(self):
        self.sender = make_user("alice")
        self.client.force_authenticate(self.sender)

    def payload(self, **extra):
        data = {
            "audio_url": AUDIO_URL,
            "transcript": "보고 싶어",
            "paper_color": "pink",
            "title": "첫 편지",
            "recipients": [{"email": "bob@example.com"}],
        }
        data.update(extra)
        return data

    def test_requires_authentication(self):
        self.client.force_authenticate(None)
        res = self.client.post(self.url, self.payload(), format="json")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_immediate_letter_is_sent_and_emailed(self):
        res = self.client.post(self.url, self.payload(), format="json")

        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.content)
        letter = Letter.objects.get()
        self.assertEqual(letter.sender, self.sender)
        self.assertTrue(letter.is_sent)
        self.assertIsNotNone(letter.scheduled_at)
        self.assertEqual(letter.recipients.get().email, "bob@example.com")

        # Celery 태스크가 즉시 실행되어 메일이 1통 발송된다.
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["bob@example.com"])
        self.assertIn(f"/share/{letter.id}", mail.outbox[0].body)

    def test_future_letter_is_not_sent_yet(self):
        future = (timezone.now() + timedelta(days=1)).isoformat()
        res = self.client.post(self.url, self.payload(scheduled_at=future), format="json")

        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.content)
        self.assertFalse(Letter.objects.get().is_sent)
        self.assertEqual(len(mail.outbox), 0)

    def test_past_scheduled_at_is_rejected(self):
        past = (timezone.now() - timedelta(hours=1)).isoformat()
        res = self.client.post(self.url, self.payload(scheduled_at=past), format="json")

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("scheduled_at", res.json())
        self.assertFalse(Letter.objects.exists())

    def test_audio_url_is_required(self):
        data = self.payload()
        del data["audio_url"]
        res = self.client.post(self.url, data, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_sender_cannot_be_spoofed(self):
        other = make_user("mallory")
        self.client.post(self.url, self.payload(sender=other.id), format="json")
        self.assertEqual(Letter.objects.get().sender, self.sender)

    def test_response_audio_url_is_presigned(self):
        res = self.client.post(self.url, self.payload(), format="json")
        url = res.json()["audio_url"]
        self.assertIn("X-Amz-Signature", url)
        self.assertEqual(urlparse(url).path, "/uploads/sample.webm")


class LetterReadTest(APITestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.carol = make_user("carol")
        self.to_bob = make_letter(self.alice, [{"email": self.bob.email}], title="to bob")
        self.to_carol = make_letter(self.alice, [{"user": self.carol}], title="to carol")

    def titles(self, res):
        return {item["title"] for item in res.json()}

    def test_list_requires_authentication(self):
        res = self.client.get(reverse("letter-list"))
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_sender_sees_all_sent_letters(self):
        self.client.force_authenticate(self.alice)
        res = self.client.get(reverse("letter-list"))
        self.assertEqual(self.titles(res), {"to bob", "to carol"})

    def test_recipient_sees_only_own_letters(self):
        self.client.force_authenticate(self.bob)
        res = self.client.get(reverse("letter-list"))
        self.assertEqual(self.titles(res), {"to bob"})

        self.client.force_authenticate(self.carol)
        res = self.client.get(reverse("letter-list"))
        self.assertEqual(self.titles(res), {"to carol"})

    def test_detail(self):
        self.client.force_authenticate(self.bob)
        res = self.client.get(reverse("letter-detail", args=[self.to_bob.id]))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["sender"]["display_id"], "alice")
        self.assertEqual(res.json()["recipients"][0]["email"], self.bob.email)

    def test_public_share_link_without_login(self):
        res = self.client.get(reverse("public-letter-detail", args=[self.to_bob.id]))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["transcript"], "안녕")

    def test_public_share_link_unknown_id(self):
        res = self.client.get(reverse("public-letter-detail", args=["00000000-0000-0000-0000-000000000000"]))
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)


class LetterTranscriptUpdateTest(APITestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.letter = make_letter(self.alice)
        self.url = reverse("letter-transcript-update", args=[self.letter.id])

    def test_sender_can_edit_transcript(self):
        self.client.force_authenticate(self.alice)
        res = self.client.patch(self.url, {"transcript": "수정된 내용"}, format="json")

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.letter.refresh_from_db()
        self.assertEqual(self.letter.transcript, "수정된 내용")

    def test_other_user_cannot_edit(self):
        self.client.force_authenticate(make_user("mallory"))
        res = self.client.patch(self.url, {"transcript": "해킹"}, format="json")

        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.letter.refresh_from_db()
        self.assertEqual(self.letter.transcript, "안녕")


class S3UploadTest(APITestCase):
    url = reverse("letter-upload")

    def setUp(self):
        self.client.force_authenticate(make_user("alice"))

    def test_requires_file(self):
        res = self.client.post(self.url, {}, format="multipart")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    @mock.patch("letters.views.boto3.client")
    def test_uploads_to_bucket_and_returns_url(self, mock_client):
        file = SimpleUploadedFile("voice.webm", b"fake-audio", content_type="audio/webm")
        res = self.client.post(self.url, {"file": file}, format="multipart")

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        upload = mock_client.return_value.upload_fileobj
        upload.assert_called_once()
        _, bucket, key = upload.call_args.args
        self.assertEqual(bucket, "dearvoice-test-bucket")
        self.assertTrue(key.startswith("uploads/") and key.endswith(".webm"))
        self.assertEqual(res.json()["url"], bucket_url(key))


class TranscribeViewTest(APITestCase):
    url = reverse("letter-transcribe")

    def setUp(self):
        self.client.force_authenticate(make_user("alice"))

    def test_requires_audio_url(self):
        res = self.client.post(self.url, {}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    @mock.patch("letters.views.clova_stt_from_file", return_value="안녕하세요")
    def test_success(self, mock_stt):
        res = self.client.post(self.url, {"audio_url": AUDIO_URL}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["transcript"], "안녕하세요")
        mock_stt.assert_called_once_with(AUDIO_URL)

    @mock.patch("letters.views.clova_stt_from_file", return_value=None)
    def test_failure(self, mock_stt):
        res = self.client.post(self.url, {"audio_url": AUDIO_URL}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(res.json()["success"])


class SendLetterTaskTest(TestCase):
    def setUp(self):
        self.alice = make_user("alice")

    def test_sends_to_valid_emails_only(self):
        letter = make_letter(self.alice, [
            {"email": "bob@example.com"},
            {"email": "not-an-email"},
            {"user": make_user("carol")},  # 이메일 필드가 비어 있음
        ])

        send_letter_task(letter.id)

        self.assertEqual([m.to for m in mail.outbox], [["bob@example.com"]])
        letter.refresh_from_db()
        self.assertTrue(letter.is_sent)

    def test_not_marked_sent_when_no_mail_went_out(self):
        letter = make_letter(self.alice, [{"email": "not-an-email"}])
        send_letter_task(letter.id)
        letter.refresh_from_db()
        self.assertFalse(letter.is_sent)

    def test_unknown_letter_does_not_raise(self):
        send_letter_task("00000000-0000-0000-0000-000000000000")

    def test_scheduled_task_sends_only_due_letters(self):
        now = timezone.now()
        due = make_letter(self.alice, [{"email": "due@example.com"}], scheduled_at=now - timedelta(minutes=1))
        later = make_letter(self.alice, [{"email": "later@example.com"}], scheduled_at=now + timedelta(hours=1))
        make_letter(self.alice, [{"email": "done@example.com"}], scheduled_at=now - timedelta(hours=1), is_sent=True)

        send_scheduled_letters()

        self.assertEqual([m.to for m in mail.outbox], [["due@example.com"]])
        due.refresh_from_db()
        later.refresh_from_db()
        self.assertTrue(due.is_sent)
        self.assertFalse(later.is_sent)
