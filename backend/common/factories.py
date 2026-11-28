"""테스트에서 공통으로 쓰는 데이터 생성 함수."""
from django.contrib.auth import get_user_model
from django.conf import settings

DEFAULT_PASSWORD = "Testpass!234"


def make_user(user_id="alice", email=None, password=DEFAULT_PASSWORD, **extra):
    User = get_user_model()
    return User.objects.create_user(
        user_id=user_id,
        email=email or f"{user_id}@example.com",
        password=password,
        **extra,
    )


def bucket_url(key):
    """테스트 설정의 S3 버킷 주소를 만든다."""
    return (
        f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3."
        f"{settings.AWS_S3_REGION_NAME}.amazonaws.com/{key}"
    )
