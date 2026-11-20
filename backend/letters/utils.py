import json
import logging
import os
import tempfile

import ffmpeg
import requests
from django.conf import settings
from django.core.mail import send_mail

from letters.models import Letter
from common.s3 import read_object

logger = logging.getLogger(__name__)

# ClovaSpeech 장문 인식은 sync 모드에서도 변환이 끝날 때까지 응답을 기다리므로 넉넉하게 잡는다.
CLOVA_SPEECH_TIMEOUT = 120  # 초


def convert_webm_to_wav(file_url):
    """S3의 webm 파일을 16kHz 모노 wav로 변환하고 wav 파일 경로를 돌려준다.

    ClovaSpeech 지원 형식에 WebM이 없어서 wav로 바꿔서 보낸다.
    돌려받은 wav 파일은 호출한 쪽에서 지워야 한다.
    """
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as input_file:
        # S3 API로 webm 파일 읽기 (비공개 버킷이라 일반 주소로는 받을 수 없음)
        input_file.write(read_object(file_url))
    output_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    output_file.close()

    try:
        (
            ffmpeg.input(input_file.name)
            .output(output_file.name, ac=1, ar=16000)
            .overwrite_output()
            .run(quiet=True)
        )
    except Exception:
        os.remove(output_file.name)
        raise
    finally:
        os.remove(input_file.name)

    return output_file.name


def request_clova_speech(wav_path):
    """ClovaSpeech 장문 인식(로컬 파일 업로드, sync)으로 wav 파일을 보내고 인식된 텍스트를 돌려준다."""
    invoke_url = (settings.CLOVA_SPEECH_INVOKE_URL or "").rstrip("/")
    secret_key = settings.CLOVA_SPEECH_SECRET_KEY
    if not invoke_url or not secret_key:
        raise RuntimeError("CLOVA_SPEECH_INVOKE_URL, CLOVA_SPEECH_SECRET_KEY 환경변수가 필요합니다.")

    params = {
        "language": "ko-KR",
        "completion": "sync",
        "wordAlignment": False,
        "fullText": True,
        "diarization": {"enable": False},
    }
    headers = {
        "Accept": "application/json;UTF-8",
        "X-CLOVASPEECH-API-KEY": secret_key,
    }

    with open(wav_path, "rb") as wav_file:
        files = {
            "media": wav_file,
            "params": (None, json.dumps(params), "application/json"),
        }
        response = requests.post(
            f"{invoke_url}/recognizer/upload",
            headers=headers,
            files=files,
            timeout=CLOVA_SPEECH_TIMEOUT,
        )
    response.raise_for_status()

    result = response.json()
    if result.get("result") != "COMPLETED":
        raise RuntimeError(f"ClovaSpeech 인식 실패: {result.get('result')} {result.get('message')}")
    return result.get("text", "")


def clova_stt_from_file(file_url):
    """S3 음성 파일을 텍스트로 변환한다. 실패하면 None을 돌려준다."""
    wav_path = None
    try:
        wav_path = convert_webm_to_wav(file_url)
        return request_clova_speech(wav_path)
    except Exception as e:
        logger.error(f"[STT 변환 실패]: {e}")
        return None
    finally:
        if wav_path and os.path.exists(wav_path):
            os.remove(wav_path)


def send_letter_email(email, letter_id):
    try:
        letter = Letter.objects.get(id=letter_id)
        letter_url = f"{settings.FRONTEND_BASE_URL}/share/{letter.id}"

        print(f"[DEBUG] 이메일 링크: {letter_url}")
        
        send_mail(
            subject="DearVoice에서 새로운 보이스레터가 도착했습니다",
            message=f"DearVoice에서 새로운 보이스레터를 받았습니다.\n아래 링크를 클릭하여 편지를 확인하세요:\n{letter_url}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )
    except Exception as e:
        logger.error(f"[이메일] 전송 실패: {e}")