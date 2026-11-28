"""하늘 편지(skyvoice) API / AI 답장 서비스 테스트.

OpenAI, Google TTS, S3, CLOVA 는 모두 mock 으로 대체한다.
"""
from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

from django.core import mail
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from common.factories import bucket_url, make_user
from skyvoice import services
from skyvoice.models import SkyVoiceLetter
from skyvoice.tasks import generate_ai_reply_async, send_scheduled_voiceletters

AUDIO_URL = bucket_url("uploads/sky.webm")
GOOD_REPLY = "나는 네 편지를 읽고 마음이 따뜻해졌단다. 늘 네 곁에서 응원하고 있을게."


def make_sky_letter(user, **extra):
    data = dict(
        receiver_name="할머니", receiver_gender="여", receiver_age=80,
        receiver_type="할머니", content_text="할머니 보고 싶어요",
    )
    data.update(extra)
    return SkyVoiceLetter.objects.create(user=user, **data)


def fake_openai(*replies):
    """chat.completions.create 가 replies 를 차례로 돌려주는 가짜 OpenAI 클라이언트."""
    client = mock.Mock()
    client.chat.completions.create.side_effect = [
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=r))])
        for r in replies
    ]
    return client


class PromptTest(TestCase):
    def setUp(self):
        self.user = make_user("alice", nickname="앨리스")

    def test_grandparent_role_and_letter_content(self):
        prompt = services.build_dynamic_prompt(make_sky_letter(self.user))
        self.assertIn("조부모", prompt)
        self.assertIn("앨리스", prompt)
        self.assertIn("할머니 보고 싶어요", prompt)

    def test_friend_role(self):
        letter = make_sky_letter(self.user, receiver_type="친구", receiver_name="민수")
        self.assertIn("친구 민수", services.build_dynamic_prompt(letter))

    def test_deceased_note_adds_afterlife_setting(self):
        alive = make_sky_letter(self.user)
        deceased = make_sky_letter(self.user, receiver_special_note="작년에 하늘나라로 가셨어요")
        self.assertNotIn("세상을 떠난", services.build_dynamic_prompt(alive))
        self.assertIn("세상을 떠난", services.build_dynamic_prompt(deceased))


class ReplyValidationTest(SimpleTestCase):
    def test_good_reply_is_valid(self):
        invalid, reasons = services.is_invalid_reply(GOOD_REPLY, "할머니", "앨리스")
        self.assertFalse(invalid, reasons)

    def test_too_long(self):
        _, reasons = services.is_invalid_reply("나는 " + "가" * 200 + "다. 끝이다.", "할머니", "")
        self.assertIn("길이 180자 초과", reasons)

    def test_single_sentence(self):
        _, reasons = services.is_invalid_reply("나는 잘 지낸다.", "할머니", "")
        self.assertIn("문장 수 2~3 미준수", reasons)

    def test_no_first_person(self):
        _, reasons = services.is_invalid_reply("잘 지내렴. 항상 응원한다.", "할머니", "")
        self.assertIn("1인칭 표현 부족", reasons)

    def test_starts_with_receiver_name(self):
        _, reasons = services.is_invalid_reply("할머니, 나는 잘 있단다. 걱정 마.", "할머니", "")
        self.assertIn("문두 수신자 호명", reasons)

    def test_postprocess_removes_quotes(self):
        self.assertEqual(services.postprocess_reply('  "“안녕”"  '), "안녕")


class GenerateReplyTest(TestCase):
    def setUp(self):
        self.letter = make_sky_letter(make_user("alice"))

    @mock.patch("skyvoice.services.openai.OpenAI")
    def test_valid_reply_calls_gpt_once(self, mock_openai):
        mock_openai.return_value = fake_openai(GOOD_REPLY)
        self.assertEqual(services.generate_gpt_reply(self.letter), GOOD_REPLY)
        self.assertEqual(mock_openai.return_value.chat.completions.create.call_count, 1)

    @mock.patch("skyvoice.services.openai.OpenAI")
    def test_invalid_reply_retries_once(self, mock_openai):
        mock_openai.return_value = fake_openai("짧다.", GOOD_REPLY)
        self.assertEqual(services.generate_gpt_reply(self.letter), GOOD_REPLY)
        self.assertEqual(mock_openai.return_value.chat.completions.create.call_count, 2)

    @mock.patch("skyvoice.services.upload_mp3_to_s3", return_value=bucket_url("skyvoice/reply/r.mp3"))
    @mock.patch("skyvoice.services.synthesize_speech", return_value=b"mp3-bytes")
    @mock.patch("skyvoice.services.generate_gpt_reply", return_value=GOOD_REPLY)
    def test_make_ai_reply_saves_text_and_voice(self, mock_gpt, mock_tts, mock_upload):
        services.make_ai_reply(self.letter)

        self.letter.refresh_from_db()
        self.assertEqual(self.letter.reply_text, GOOD_REPLY)
        self.assertEqual(self.letter.reply_voice_url, bucket_url("skyvoice/reply/r.mp3"))
        self.assertIsNotNone(self.letter.replied_at)
        mock_tts.assert_called_once_with(GOOD_REPLY)

    @mock.patch("skyvoice.services.synthesize_speech", side_effect=RuntimeError("TTS down"))
    @mock.patch("skyvoice.services.generate_gpt_reply", return_value=GOOD_REPLY)
    def test_make_ai_reply_tts_failure_does_not_raise(self, mock_gpt, mock_tts):
        self.assertIsNone(services.make_ai_reply(self.letter))
        self.letter.refresh_from_db()
        self.assertEqual(self.letter.reply_text, "")

    @mock.patch("skyvoice.services.boto3.client")
    def test_upload_mp3_to_s3(self, mock_client):
        url = services.upload_mp3_to_s3(b"mp3", "reply.mp3")
        mock_client.return_value.put_object.assert_called_once_with(
            Bucket="dearvoice-test-bucket", Key="skyvoice/reply/reply.mp3",
            Body=b"mp3", ContentType="audio/mpeg",
        )
        self.assertEqual(url, bucket_url("skyvoice/reply/reply.mp3"))


class SkyLetterCreateTest(APITestCase):
    url = reverse("skyvoice-letter-create")

    def setUp(self):
        self.user = make_user("alice")
        self.client.force_authenticate(self.user)

    def payload(self, **extra):
        data = {
            "receiver_name": "할머니", "receiver_gender": "여", "receiver_age": 80,
            "receiver_type": "할머니", "audio_url": AUDIO_URL, "title": "보고 싶어요",
        }
        data.update(extra)
        return data

    def test_requires_authentication(self):
        self.client.force_authenticate(None)
        res = self.client.post(self.url, self.payload(), format="json")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    @mock.patch("skyvoice.views.generate_ai_reply_async.delay")
    @mock.patch("skyvoice.views.clova_stt_from_file", return_value="할머니 보고 싶어요")
    def test_create_runs_stt_and_queues_ai_reply(self, mock_stt, mock_delay):
        res = self.client.post(self.url, self.payload(), format="json")

        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.content)
        letter = SkyVoiceLetter.objects.get()
        self.assertEqual(letter.user, self.user)
        self.assertEqual(letter.content_text, "할머니 보고 싶어요")
        self.assertTrue(letter.is_sent)
        mock_stt.assert_called_once_with(AUDIO_URL)
        mock_delay.assert_called_once_with(letter.id)

    @mock.patch("skyvoice.views.generate_ai_reply_async.delay")
    @mock.patch("skyvoice.views.clova_stt_from_file", return_value=None)
    def test_stt_failure_skips_ai_reply(self, mock_stt, mock_delay):
        res = self.client.post(self.url, self.payload(), format="json")

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(SkyVoiceLetter.objects.get().content_text, "[음성 텍스트 변환 실패]")
        mock_delay.assert_not_called()

    @mock.patch("skyvoice.views.generate_ai_reply_async.delay")
    @mock.patch("skyvoice.views.clova_stt_from_file", return_value="내용")
    def test_future_letter_is_not_sent_yet(self, mock_stt, mock_delay):
        future = (timezone.now() + timedelta(days=1)).isoformat()
        self.client.post(self.url, self.payload(scheduled_at=future), format="json")
        self.assertFalse(SkyVoiceLetter.objects.get().is_sent)

    def test_missing_receiver_info(self):
        res = self.client.post(self.url, {"audio_url": AUDIO_URL}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        for field in ("receiver_name", "receiver_gender", "receiver_age", "receiver_type"):
            self.assertIn(field, res.json())

    def test_user_cannot_be_spoofed(self):
        other = make_user("mallory")
        with mock.patch("skyvoice.views.clova_stt_from_file", return_value=None):
            self.client.post(self.url, self.payload(user=other.id), format="json")
        self.assertEqual(SkyVoiceLetter.objects.get().user, self.user)


class SkyLetterReadTest(APITestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.letter = make_sky_letter(self.alice, title="alice letter")
        make_sky_letter(make_user("bob"), title="bob letter")

    def test_list_shows_only_my_letters(self):
        self.client.force_authenticate(self.alice)
        res = self.client.get(reverse("skyvoice-letter-list"))
        self.assertEqual([i["title"] for i in res.json()], ["alice letter"])

    def test_owner_can_see_detail(self):
        self.client.force_authenticate(self.alice)
        res = self.client.get(reverse("skyvoice-letter-detail", args=[self.letter.id]))
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_other_user_cannot_see_detail(self):
        self.client.force_authenticate(make_user("mallory"))
        res = self.client.get(reverse("skyvoice-letter-detail", args=[self.letter.id]))
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_requires_authentication(self):
        res = self.client.get(reverse("skyvoice-letter-list"))
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_public_share_link_without_login(self):
        res = self.client.get(reverse("public-skyvoice-detail", args=[self.letter.id]))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["title"], "alice letter")

    def test_public_share_link_unknown_id(self):
        res = self.client.get(reverse("public-skyvoice-detail", args=[999999]))
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)


class SkyTranscribeTest(APITestCase):
    url = reverse("skyvoice-letter-transcribe")

    def setUp(self):
        self.client.force_authenticate(make_user("alice"))

    def test_requires_audio_url(self):
        res = self.client.post(self.url, {}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    @mock.patch("skyvoice.views.clova_stt_from_file", return_value="안녕")
    def test_success(self, mock_stt):
        res = self.client.post(self.url, {"audio_url": AUDIO_URL}, format="json")
        self.assertEqual(res.json(), {"transcript": "안녕", "success": True})

    @mock.patch("skyvoice.views.clova_stt_from_file", return_value=None)
    def test_failure(self, mock_stt):
        res = self.client.post(self.url, {"audio_url": AUDIO_URL}, format="json")
        self.assertEqual(res.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)


class SkyTasksTest(TestCase):
    def setUp(self):
        self.alice = make_user("alice")

    @mock.patch("skyvoice.tasks.make_ai_reply")
    def test_generate_ai_reply_async(self, mock_reply):
        letter = make_sky_letter(self.alice)
        generate_ai_reply_async(letter.id)
        mock_reply.assert_called_once_with(letter)

    @mock.patch("skyvoice.tasks.make_ai_reply")
    def test_generate_ai_reply_unknown_letter(self, mock_reply):
        generate_ai_reply_async(999999)
        mock_reply.assert_not_called()

    def test_scheduled_task_notifies_due_letters(self):
        now = timezone.now()
        due = make_sky_letter(self.alice, scheduled_at=now - timedelta(minutes=1))
        later = make_sky_letter(self.alice, scheduled_at=now + timedelta(hours=1))

        send_scheduled_voiceletters()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.alice.email])
        due.refresh_from_db()
        later.refresh_from_db()
        self.assertTrue(due.is_sent)
        self.assertFalse(later.is_sent)
