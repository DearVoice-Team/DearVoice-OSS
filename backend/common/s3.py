"""비공개 S3 버킷에 저장된 음성 파일을 다루는 함수.

DB에는 업로드할 때 만든 S3 주소를 그대로 저장하고,
- 응답으로 내보낼 때는 presigned_url()로 임시 주소로 바꾸고
- 서버에서 파일이 필요할 때는 read_object()로 S3 API를 통해 읽는다.
"""
import logging
from functools import lru_cache
from urllib.parse import unquote, urlparse

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings

logger = logging.getLogger(__name__)

PRESIGNED_URL_EXPIRES = 60 * 60  # 임시 주소 유효 시간(초): 1시간


@lru_cache(maxsize=1)
def _s3_client():
    # 리전 주소(버킷.s3.리전.amazonaws.com)로 서명해야 다른 리전으로 돌려보내지는 문제가 없다.
    return boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME,
        endpoint_url=f"https://s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com",
        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
    )


def key_from_url(url):
    """우리 버킷의 S3 주소면 객체 키를 돌려주고, 아니면 None을 돌려준다."""
    if not url:
        return None
    parsed = urlparse(url)
    bucket_host = (
        f"{settings.AWS_STORAGE_BUCKET_NAME}.s3."
        f"{settings.AWS_S3_REGION_NAME}.amazonaws.com"
    )
    if parsed.scheme != "https" or parsed.netloc != bucket_host:
        return None
    return unquote(parsed.path.lstrip("/")) or None


def presigned_url(url, expires=PRESIGNED_URL_EXPIRES):
    """우리 버킷 주소를 임시 주소로 바꾼다. 다른 주소나 빈 값은 그대로 돌려준다."""
    key = key_from_url(url)
    if key is None:
        return url
    try:
        return _s3_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.AWS_STORAGE_BUCKET_NAME, "Key": key},
            ExpiresIn=expires,
        )
    except (BotoCoreError, ClientError) as e:
        logger.warning("[S3] 임시 주소 생성 실패: key=%s, error=%s", key, e)
        return url


def read_object(url):
    """우리 버킷의 파일을 S3 API로 읽는다. 다른 주소는 거부한다."""
    key = key_from_url(url)
    if key is None:
        raise ValueError("허용되지 않은 음성 파일 주소입니다.")
    response = _s3_client().get_object(
        Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=key
    )
    return response["Body"].read()
