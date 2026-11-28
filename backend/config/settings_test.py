"""테스트 / CI 전용 설정.

실행: python manage.py test --settings=config.settings_test

- 외부 서비스(MySQL, Redis, S3, OpenAI, CLOVA, Google TTS, SMTP) 없이 테스트가 돌도록
  DB는 메모리 SQLite, 메일은 메모리, Celery는 즉시 실행으로 바꾼다.
- 실제 키가 들어 있는 backend/.env 가 있어도 아래 값으로 덮어써서 외부 API를 호출하지 않는다.
"""
import os

# settings.py 가 SECRET_KEY 를 필수로 읽기 때문에 import 전에 테스트용 값을 넣어 둔다.
os.environ.setdefault("SECRET_KEY", "test-secret-key-only-for-ci")

from .settings import *  # noqa: E402,F401,F403

SECRET_KEY = "test-secret-key-only-for-ci"
DEBUG = False

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# 비밀번호 해시를 가볍게 해서 테스트 속도 개선
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# 실제 메일 대신 django.core.mail.outbox 에 쌓인다.
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
DEFAULT_FROM_EMAIL = "noreply@dearvoice.test"

# Redis 없이 .delay() / .apply_async() 가 바로 실행되도록
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"

# 외부 서비스 키는 모두 가짜 값 (테스트에서는 mock 으로 대체)
AWS_ACCESS_KEY_ID = "test"
AWS_SECRET_ACCESS_KEY = "test"
AWS_STORAGE_BUCKET_NAME = "dearvoice-test-bucket"
AWS_S3_REGION_NAME = "ap-northeast-2"
AWS_S3_CUSTOM_DOMAIN = f"{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com"
CLOVA_SPEECH_INVOKE_URL = ""
CLOVA_SPEECH_SECRET_KEY = ""
OPENAI_API_KEY = "test"
GOOGLE_CLIENT_ID = "test-client-id.apps.googleusercontent.com"
FRONTEND_BASE_URL = "http://testserver-frontend"

# Jenkins 에서 --testrunner xmlrunner.extra.djangotestrunner.XMLTestRunner 로 실행하면
# 이 폴더에 JUnit XML 리포트가 만들어진다.
TEST_OUTPUT_DIR = os.getenv("TEST_OUTPUT_DIR", "test-reports")
TEST_OUTPUT_FILE_NAME = "backend-junit.xml"
