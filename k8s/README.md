# DearVoice Kubernetes 인프라

로컬 클러스터(Docker Desktop Kubernetes)에서 먼저 띄우고, 나중에 클라우드로 옮길 수 있도록
특정 환경에 묶이지 않는 기본 YAML 로 작성했습니다.

## 폴더 구조

```
k8s/
├── kustomization.yaml          # kubectl apply -k k8s 로 한 번에 적용
├── namespace.yaml              # dearvoice 네임스페이스
├── config/
│   ├── backend-configmap.yaml       # 비밀이 아닌 backend 설정
│   ├── backend-secret.example.yaml  # backend 비밀 값 예시 (복사해서 사용)
│   └── mysql-secret.example.yaml    # MySQL 계정 예시 (복사해서 사용)
├── scripts/
│   └── create-secrets.ps1      # backend/.env 로 실제 Secret 만들기
├── mysql/                      # MySQL 8.0 StatefulSet + Service (PVC 5Gi)
├── redis/                      # Redis 7 StatefulSet + Service (PVC 1Gi)
├── ingress/
│   └── ingress.yaml            # 경로별 라우팅 규칙 (/api 등 → backend, / → frontend)
├── ingress-controller/
│   └── traefik.yaml            # Traefik Ingress Controller (클러스터에 한 번만 설치)
└── examples/
    └── dummy-apps.yaml         # [테스트용] 라우팅 확인용 임시 backend / frontend
```

## 용어 한 줄 정리

| 용어 | 뜻 |
| --- | --- |
| Namespace | 클러스터 안의 폴더. DearVoice 리소스는 모두 `dearvoice` 에 둡니다. |
| StatefulSet | 데이터를 가진 앱(DB)용 배포 방식. 파드 이름(`mysql-0`)과 디스크가 고정됩니다. |
| PVC | 디스크 요청서. 파드가 다시 떠도 데이터가 남습니다. |
| Service | 파드에 붙는 고정 주소. 클러스터 안에서 `mysql`, `redis` 라는 이름으로 접속합니다. |
| ConfigMap / Secret | 환경변수 묶음. 비밀이 아닌 값은 ConfigMap, 비밀 값은 Secret 에 둡니다. |
| Ingress | 외부 요청을 경로(`/api` 등)에 따라 알맞은 Service 로 보내는 규칙입니다. |

## 처음 한 번: 로컬 클러스터 준비

1. 관리자 PowerShell 에서 `wsl --install --no-distribution` 실행 후 재부팅
2. `winget install -e --id Docker.DockerDesktop`
3. Docker Desktop → Settings → Kubernetes → Enable Kubernetes → Apply
4. 확인: `kubectl config use-context docker-desktop` → `kubectl get nodes` 에서 `Ready`

## 배포 순서

```powershell
# 0) Ingress Controller(Traefik) 설치 (클러스터마다 처음 한 번만)
kubectl apply -f k8s/ingress-controller/traefik.yaml

# 1) 네임스페이스, ConfigMap, MySQL, Redis, Ingress 적용
kubectl apply -k k8s

# 2) backend/.env 로 실제 Secret 만들기 (mysql-secret, backend-secret, google-tts-key)
powershell -ExecutionPolicy Bypass -File k8s/scripts/create-secrets.ps1

# 3) 상태 확인 (mysql-0, redis-0 이 Running, READY 1/1 이면 성공)
kubectl -n dearvoice get pods,pvc,svc
```

> Secret 을 1번보다 늦게 만들면 MySQL 파드가 처음에 `CreateContainerConfigError` 로 기다립니다.
> Secret 을 만들면 자동으로 다시 시작되니 걱정하지 않아도 됩니다.

### Secret 만들기 스크립트 (`scripts/create-secrets.ps1`)

`backend/.env` 를 읽어서 Secret 3개를 만듭니다. 비밀 값은 화면에 출력하지 않고 파일로도 남기지 않습니다.

| Secret | 내용 |
| --- | --- |
| `mysql-secret` | MySQL 계정. **이미 있으면 그대로 둡니다.** 없으면 비밀번호를 무작위로 만듭니다. |
| `backend-secret` | `.env` 의 비밀 값 + `mysql-secret` 의 DB 계정 (`DB_USER`, `DB_PASSWORD`) |
| `google-tts-key` | `.env` 의 `GOOGLE_APPLICATION_CREDENTIALS` 경로에 있는 키 파일 |

- `.env` 의 `DB_USER` / `DB_PASSWORD` 는 내 PC 의 MySQL 용이라 쓰지 않습니다.
  클러스터 안 MySQL 계정은 `mysql-secret` 이 기준입니다.
- 다시 실행해도 안전합니다. `.env` 를 고쳤으면 다시 실행한 뒤 backend 를 재시작합니다.
  `kubectl -n dearvoice rollout restart deployment/backend`
- 예시 값(`your-...`, `change-me`) 그대로이거나 빠진 키는 `[경고]` 로 알려줍니다.
- MySQL 은 **처음 시작할 때만** 계정을 만듭니다. `mysql-secret` 을 지우고 새로 만들면
  DB 안의 비밀번호와 달라져 접속이 안 됩니다. 처음부터 다시 하려면 PVC 까지 지워야 합니다.
- 스크립트 없이 직접 만들고 싶으면 `config/*-secret.example.yaml` 을 복사해서 값을 채운 뒤
  `kubectl apply -f` 로 적용해도 됩니다. (복사본은 git 에 올라가지 않음)

## 연결 확인

```powershell
# Redis: PONG 이 나오면 성공
kubectl -n dearvoice exec redis-0 -- redis-cli ping

# MySQL: 클러스터 안에서 임시 클라이언트 파드로 접속 (비밀번호를 물어봅니다)
kubectl -n dearvoice run mysql-client --rm -it --image=mysql:8.0 --restart=Never -- mysql -h mysql -u dearvoice_dev -p dearvoice_db

# 내 PC 에서 접속하고 싶을 때: 로컬 MySQL80 이 3306 을 쓰므로 13306 으로 연결
kubectl -n dearvoice port-forward svc/mysql 13306:3306
```

## backend 가 받을 환경변수 (backend/.env 기준)

| 키 | 위치 | 비고 |
| --- | --- | --- |
| DEBUG, ALLOWED_HOSTS, FRONTEND_BASE_URL, CORS_ALLOWED_ORIGINS | backend-config | |
| DB_HOST, DB_PORT, DB_NAME | backend-config | `DB_HOST=mysql` |
| CELERY_BROKER_URL, CELERY_RESULT_BACKEND | backend-config | `redis://redis:6379/0` |
| AWS_S3_REGION_NAME, AWS_STORAGE_BUCKET_NAME, GOOGLE_CLIENT_ID | backend-config | 공개 값 |
| GOOGLE_APPLICATION_CREDENTIALS | backend-config | 파일 경로 `/var/secrets/google/google-tts.json` |
| SECRET_KEY, DB_USER, DB_PASSWORD | backend-secret | |
| AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY | backend-secret | |
| CLOVA_SPEECH_SECRET_KEY, CLOVA_SPEECH_INVOKE_URL, OPENAI_API_KEY | backend-secret | |
| EMAIL_HOST_USER, EMAIL_HOST_PASSWORD | backend-secret | |

CD 담당 backend Deployment 에서는 아래처럼 연결하면 됩니다.

```yaml
envFrom:
  - configMapRef: { name: backend-config }
  - secretRef: { name: backend-secret }
volumeMounts:
  - { name: google-tts-key, mountPath: /var/secrets/google, readOnly: true }
volumes:
  - name: google-tts-key
    secret: { secretName: google-tts-key }
```

## Ingress 라우팅

```
브라우저 ── http://localhost ──▶ Ingress Controller
                                   ├─ /api/*       ─▶ Service backend:8000  (Django REST API)
                                   ├─ /skyvoice/*  ─▶ Service backend:8000  (하늘편지 API)
                                   ├─ /admin/*     ─▶ Service backend:8000  (Django 관리자)
                                   └─ /*           ─▶ Service frontend:80   (nginx + React 빌드)
```

- 프론트와 API 가 같은 주소(origin)를 쓰므로 CORS 설정이 거의 필요 없고,
  프론트의 `VITE_SERVER_API_URL` 은 같은 주소(로컬: `http://localhost`)로 두면 됩니다.
- Django `urls.py` 가 `/api/`, `/skyvoice/`, `/admin/` 로 시작하므로 경로를 잘라내지(rewrite) 않습니다.
- 정적 파일·미디어는 S3 에서 바로 내려주므로 Ingress 경로가 필요 없습니다.
- Ingress Controller 는 **Traefik** 을 씁니다. 많이 쓰이던 ingress-nginx 는 2026년 3월에
  유지보수가 종료되었기 때문입니다. Ingress YAML 은 표준이라 Controller 를 바꿔도
  `ingressClassName` 한 줄만 고치면 됩니다.
- Docker Desktop 에서는 Traefik 의 LoadBalancer Service 가 내 PC 의 `localhost:80` 으로 열립니다.
  80 번 포트를 다른 프로그램이 쓰고 있으면 열리지 않으니 먼저 꺼 주세요.
- Traefik 은 Prefix 를 글자 기준으로 비교해서 `/apix` 같은 경로도 backend 로 갑니다.
  프론트에 `/api`, `/skyvoice`, `/admin` 으로 시작하는 화면 경로만 만들지 않으면 문제없습니다.
- 클라우드로 옮길 때는 `rules` 에 `host: <도메인>` 과 `tls` 를 추가합니다.
- `backend`, `frontend` Service 이름과 포트는 CD 담당 Deployment 와 맞춰야 합니다.

### 임시 앱으로 라우팅 확인하기

실제 backend / frontend 이미지가 없어도 요청 정보를 보여주는 임시 앱으로 라우팅을 확인할 수 있습니다.

```powershell
kubectl apply -f k8s/examples/dummy-apps.yaml
curl.exe http://localhost/            # Name: dummy-frontend
curl.exe http://localhost/api/        # Name: dummy-backend
curl.exe http://localhost/skyvoice/   # Name: dummy-backend
curl.exe http://localhost/admin/      # Name: dummy-backend

# 실제 Deployment 를 배포하기 전에 꼭 지웁니다. (같은 이름이라 겹칩니다)
kubectl delete -f k8s/examples/dummy-apps.yaml
```

## 정리(삭제)

```powershell
kubectl delete -k k8s                       # 리소스 삭제 (PVC 는 남음)
kubectl delete -f k8s/ingress-controller/traefik.yaml   # Traefik 삭제
kubectl -n dearvoice delete pvc --all       # DB 데이터까지 지우려면 (되돌릴 수 없음)
```
