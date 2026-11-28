# DearVoice-OSS

> 목소리로 편지를 쓰고 전하는 음성 편지 서비스 (AI 음성 답장 포함)
> 2026학년도 2학기 오픈소스소프트웨어 2팀 프로젝트

기존 프로젝트인 **DearVoice**를 하나의 저장소로 합치고,
GitHub 협업 규칙 · Docker · Jenkins CI · Kubernetes 배포 환경을 새로 구축한 프로젝트입니다.

---

## 주요 기능

| 기능 | 설명 | API |
|------|------|-----|
| 회원가입 / 로그인 | 이메일 가입, JWT 로그인, Google 로그인 | `/api/auth/` |
| 음성 편지 | 녹음 → S3 업로드 → CLOVA STT로 텍스트 변환 → 예약 발송 · 이메일 알림 | `/api/letters/` |
| 하늘 편지 | 받는 사람 정보(관계·나이 등) 입력 → OpenAI가 그 사람이 되어 답장 생성 → Google TTS 음성 합성 | `/skyvoice/` |
| 마이페이지 | 보낸/받은 편지 목록, 읽음 처리, 회원 탈퇴 | `/api/mypage/` |
| 공유 링크 | 비회원도 이메일 링크로 편지 열람 | `/api/letters/share/<uuid>/` |

## 기술 스택

| 구분 | 사용 기술 |
|------|-----------|
| Frontend | React 19, Vite 6, React Router, Axios, nginx |
| Backend | Python 3.11, Django 4.2, Django REST Framework, SimpleJWT, Celery |
| Data | MySQL 8.0, Redis 7, AWS S3 |
| 외부 API | OpenAI, NAVER CLOVA Speech(STT), Google Cloud TTS, Gmail SMTP |
| Test | Django TestCase · DRF APITestCase, Vitest · React Testing Library |
| DevOps | Git/GitHub, Docker, Docker Compose, Docker Hub, Jenkins, Kubernetes (Traefik Ingress) |

## 아키텍처

```
브라우저 ──▶ Ingress (Traefik)
              ├─ /api, /skyvoice, /admin ─▶ backend (Django + gunicorn :8000)
              │                                ├─ MySQL
              │                                ├─ Redis ◀── celery-worker / celery-beat (예약 발송, AI 답장)
              │                                └─ S3 · OpenAI · CLOVA · Google TTS · SMTP
              └─ /*                         ─▶ frontend (nginx + React 빌드 :80)
```

## 폴더 구조

```
DearVoice-OSS/
├── frontend/dearvoice/     # React + Vite 앱, Dockerfile, nginx.conf
├── backend/                # Django 프로젝트
│   ├── config/             #   settings, urls, celery, settings_test(테스트 설정)
│   ├── users/              #   회원 / 인증
│   ├── letters/            #   음성 편지 + STT
│   ├── skyvoice/           #   하늘 편지 + AI 답장 + TTS
│   ├── mypage/             #   마이페이지
│   ├── common/             #   S3 유틸, 테스트용 데이터 생성 함수
│   └── docker-compose.yml  #   mysql, redis, backend, celery
├── k8s/                    # Kubernetes 매니페스트 (자세한 내용은 k8s/README.md)
├── docker-compose.yml      # 전체 스택 (frontend + backend compose include)
├── Jenkinsfile             # Jenkins CI 파이프라인
├── CONTRIBUTING.md         # 브랜치 / 커밋 / PR 규칙
└── .github/                # Issue · PR 템플릿
```

---

## 실행 방법

### 1. 환경변수 준비

```bash
cp backend/.env.example backend/.env                          # 값 채우기
cp frontend/dearvoice/.env.example frontend/dearvoice/.env    # 로컬 개발 서버(npm run dev)용
```

- `SECRET_KEY`, `DB_USER`, `DB_PASSWORD`는 필수입니다.
- Google TTS 서비스 계정 JSON은 `backend/secrets/google-tts.json`에 둡니다. (커밋 금지)
- 외부 API 키가 없어도 서버는 뜨지만, 해당 기능(STT, AI 답장 등)만 실패합니다.
- Docker Compose로 빌드할 때 Google 로그인을 쓰려면 루트 `.env`(또는 셸 환경변수)에 `VITE_GOOGLE_CLIENT_ID`를 넣습니다.

### 2. Docker Compose로 전체 실행 (권장)

```bash
docker compose up -d --build
```

| 서비스 | 주소 |
|--------|------|
| frontend | http://localhost:8080 |
| backend API | http://localhost:8000 |

### 3. 로컬 개발 서버

```bash
# backend (PC에 MySQL 8.0, Redis가 설치되어 있어야 함. DB_HOST=127.0.0.1)
# ※ compose의 mysql, redis는 포트를 외부에 열지 않아 로컬 runserver에서 바로 접속할 수 없습니다.
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver

# frontend (vite 프록시가 /api, /skyvoice 를 localhost:8000 으로 전달)
cd frontend/dearvoice
npm ci
npm run dev        # http://localhost:5173
```

### 4. Kubernetes

[`k8s/README.md`](k8s/README.md)를 참고하세요.
현재 MySQL · Redis · Ingress까지 구성되어 있고, backend / frontend Deployment는 CD 단계에서 추가할 예정입니다.

---

## 테스트

MySQL · Redis · 외부 API 없이 실행됩니다. (DB는 메모리 SQLite, 외부 서비스는 mock 처리)

```bash
# backend (100개)
cd backend
python manage.py test --settings=config.settings_test --buffer

# frontend (30개)
cd frontend/dearvoice
npm test                 # 한 번 실행
npm run test:watch       # 파일 저장 시 자동 실행
npm run test:coverage    # 커버리지 보고서
```

> - 백엔드 STT 테스트는 FFmpeg가 필요합니다. (Windows: `winget install Gyan.FFmpeg`)
> - `npm run lint`는 기존 코드의 오류로 실패합니다.

## CI 파이프라인 (Jenkins)

목표: `develop`, `main` 브랜치와 모든 PR에서 Jenkins가 자동으로 실행되고, 결과가 PR 체크로 표시되어 통과해야만 Merge할 수 있도록 합니다.

| 단계 | 내용 |
|------|------|
| Prepare | 커밋 해시로 이미지 태그 생성 |
| Test backend | backend 이미지 안에서 테스트 실행 + JUnit 리포트 |
| Test frontend | Vitest 테스트 실행 + JUnit 리포트 |
| Build images | frontend / backend Docker 이미지 빌드 |
| Push images | `develop` / `main` 머지 시에만 Docker Hub push |

---

## 협업 규칙

브랜치 전략, 커밋 컨벤션, PR · 코드 리뷰 규칙은 [CONTRIBUTING.md](CONTRIBUTING.md)를 따릅니다.

```
이슈 생성 → develop에서 브랜치 분기 (feature/번호-내용) → 커밋 → PR (base: develop)
→ Jenkins CI 통과 + 1명 이상 Approve → Merge → 브랜치 삭제
```

## 원본 프로젝트

- [SSWU-SW2025-DearVoice-FrontEnd](https://github.com/SSWU-SW2025-DearVoice/SSWU-SW2025-DearVoice-FrontEnd)
- [SSWU-SW2025-DearVoice-BackEnd](https://github.com/SSWU-SW2025-DearVoice/SSWU-SW2025-DearVoice-BackEnd)

## 보안

API 키, 비밀번호, `.env`, 서비스 계정 JSON 등 인증 정보는 절대 커밋하지 않습니다.
원본 저장소 이력에 노출된 키는 재사용하지 말고 새로 발급하세요.
