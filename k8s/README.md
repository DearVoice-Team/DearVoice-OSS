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
├── mysql/                      # MySQL 8.0 StatefulSet + Service (PVC 5Gi)
├── redis/                      # Redis 7 StatefulSet + Service (PVC 1Gi)
└── ingress/
    └── ingress.proposal.yaml   # Ingress 라우팅 설계안 (아직 적용 안 함)
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
# 1) 네임스페이스, ConfigMap, MySQL, Redis 적용
kubectl apply -k k8s

# 2) Secret 만들기: 예시 파일을 복사한 뒤 값을 채웁니다. (복사본은 git 에 올라가지 않음)
Copy-Item k8s/config/mysql-secret.example.yaml k8s/config/mysql-secret.yaml
Copy-Item k8s/config/backend-secret.example.yaml k8s/config/backend-secret.yaml
#    → 두 파일을 열어 값 채우기 (DB_USER/DB_PASSWORD 는 MYSQL_USER/MYSQL_PASSWORD 와 같게)
kubectl apply -f k8s/config/mysql-secret.yaml
kubectl apply -f k8s/config/backend-secret.yaml

# 3) Google TTS 키 파일은 파일 그대로 Secret 으로 만듭니다.
kubectl -n dearvoice create secret generic google-tts-key --from-file=key.json=<키 파일 경로>

# 4) 상태 확인 (mysql-0, redis-0 이 Running, READY 1/1 이면 성공)
kubectl -n dearvoice get pods,pvc,svc
```

> Secret 을 1번보다 늦게 만들면 MySQL 파드가 처음에 `CreateContainerConfigError` 로 기다립니다.
> Secret 을 만들면 자동으로 다시 시작되니 걱정하지 않아도 됩니다.

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
| GOOGLE_APPLICATION_CREDENTIALS | backend-config | 파일 경로 `/var/secrets/google/key.json` |
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

## Ingress 라우팅 설계안

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
- Ingress Controller 는 **Traefik** 을 제안합니다. 많이 쓰이던 ingress-nginx 는 2026년 3월에
  유지보수가 종료되었기 때문입니다. Ingress YAML 은 표준이라 Controller 를 바꿔도
  `ingressClassName` 한 줄만 고치면 됩니다.
- 클라우드로 옮길 때는 `rules` 에 `host: <도메인>` 과 `tls` 를 추가합니다.
- `backend`, `frontend` Service 이름과 포트는 CD 담당자와 맞춘 뒤 적용합니다.

## 정리(삭제)

```powershell
kubectl delete -k k8s                       # 리소스 삭제 (PVC 는 남음)
kubectl -n dearvoice delete pvc --all       # DB 데이터까지 지우려면 (되돌릴 수 없음)
```
