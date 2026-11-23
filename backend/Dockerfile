FROM python:3.11-slim


ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# mysqlclient 빌드용 패키지 + ffmpeg (ffmpeg-python용)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential default-libmysqlclient-dev pkg-config ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 의존성 먼저 설치 (코드만 바뀔 때 빌드 캐시 재사용)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# root가 아닌 사용자로 실행 (보안)
RUN useradd -m appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--timeout", "150"]
