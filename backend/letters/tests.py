import glob
import json
import os
import subprocess
import tempfile
from unittest import mock

import requests
from django.test import SimpleTestCase, override_settings

from letters import utils

INVOKE_URL = "https://clovaspeech-gw.ncloud.com/external/v1/1234/test-hash"


def make_webm_bytes():
    """테스트용 1초짜리 webm(opus) 음성을 ffmpeg로 만든다."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = os.path.join(tmp_dir, "sample.webm")
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                "-c:a", "libopus", path,
            ],
            check=True,
        )
        with open(path, "rb") as f:
            return f.read()


def fake_response(status_code=200, body=None):
    response = mock.Mock()
    response.status_code = status_code
    response.json.return_value = body or {}
    if status_code >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(f"{status_code} Error")
    else:
        response.raise_for_status.return_value = None
    return response


def temp_audio_files():
    tmp = tempfile.gettempdir()
    return set(glob.glob(os.path.join(tmp, "*.webm")) + glob.glob(os.path.join(tmp, "*.wav")))


@override_settings(CLOVA_SPEECH_INVOKE_URL=INVOKE_URL, CLOVA_SPEECH_SECRET_KEY="test-secret")
class ClovaSpeechSTTTest(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.webm_bytes = make_webm_bytes()

    def setUp(self):
        patcher = mock.patch.object(utils, "read_object", return_value=self.webm_bytes)
        patcher.start()
        self.addCleanup(patcher.stop)

    @mock.patch.object(utils.requests, "post")
    def test_success_returns_text(self, mock_post):
        mock_post.return_value = fake_response(body={"result": "COMPLETED", "text": "안녕하세요"})

        self.assertEqual(utils.clova_stt_from_file("https://bucket/audio.webm"), "안녕하세요")

        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], f"{INVOKE_URL}/recognizer/upload")
        self.assertEqual(kwargs["headers"]["X-CLOVASPEECH-API-KEY"], "test-secret")
        self.assertEqual(kwargs["timeout"], utils.CLOVA_SPEECH_TIMEOUT)
        params = json.loads(kwargs["files"]["params"][1])
        self.assertEqual(params["language"], "ko-KR")
        self.assertEqual(params["completion"], "sync")
        self.assertIn("media", kwargs["files"])

    @mock.patch.object(utils.requests, "post")
    def test_sends_16khz_mono_wav(self, mock_post):
        captured = {}

        def capture(url, headers, files, timeout):
            captured["data"] = files["media"].read()
            return fake_response(body={"result": "COMPLETED", "text": "ok"})

        mock_post.side_effect = capture
        utils.clova_stt_from_file("https://bucket/audio.webm")

        wav = captured["data"]
        self.assertEqual(wav[:4], b"RIFF")
        self.assertEqual(wav[8:12], b"WAVE")
        self.assertEqual(int.from_bytes(wav[22:24], "little"), 1)  # 채널 수
        self.assertEqual(int.from_bytes(wav[24:28], "little"), 16000)  # 샘플레이트

    @mock.patch.object(utils.requests, "post")
    def test_http_error_returns_none(self, mock_post):
        mock_post.return_value = fake_response(status_code=401)
        self.assertIsNone(utils.clova_stt_from_file("https://bucket/audio.webm"))

    @mock.patch.object(utils.requests, "post")
    def test_failed_result_returns_none(self, mock_post):
        mock_post.return_value = fake_response(body={"result": "FAILED", "message": "Invalid audio"})
        self.assertIsNone(utils.clova_stt_from_file("https://bucket/audio.webm"))

    @mock.patch.object(utils.requests, "post")
    def test_timeout_returns_none(self, mock_post):
        mock_post.side_effect = requests.Timeout("timeout")
        self.assertIsNone(utils.clova_stt_from_file("https://bucket/audio.webm"))

    @override_settings(CLOVA_SPEECH_INVOKE_URL="", CLOVA_SPEECH_SECRET_KEY="")
    @mock.patch.object(utils.requests, "post")
    def test_missing_settings_returns_none(self, mock_post):
        self.assertIsNone(utils.clova_stt_from_file("https://bucket/audio.webm"))
        mock_post.assert_not_called()

    @mock.patch.object(utils.requests, "post")
    def test_temp_files_are_removed(self, mock_post):
        mock_post.return_value = fake_response(body={"result": "COMPLETED", "text": "ok"})
        before = temp_audio_files()
        utils.clova_stt_from_file("https://bucket/audio.webm")
        mock_post.side_effect = requests.Timeout("timeout")
        utils.clova_stt_from_file("https://bucket/audio.webm")
        self.assertEqual(temp_audio_files() - before, set())
