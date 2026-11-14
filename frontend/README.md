# DearVoice-OSS

2026학년도 2학기 오픈소스소프트웨어 팀 프로젝트

## 프로젝트 소개

DearVoice는 음성 편지를 작성하고 전달할 수 있으며
AI를 활용한 답장 생성 및 음성 변환 기능을 제공하는 서비스입니다.

기존 2025학년도 소프트웨어경진대회 출품 프로젝트인
DearVoice를 기반으로 개발 및 협업 환경을 개선하고
CI/CD 파이프라인을 구축하였습니다.

## 프로젝트 목표

- GitHub 기반 팀 협업 환경 구축
- Branch 및 Commit 관리
- Pull Request 기반 개발 Workflow 적용
- Docker를 활용한 서비스 컨테이너화
- Jenkins를 활용한 CI/CD 파이프라인 구축
- Kubernetes를 활용한 서비스 배포 자동화

## Technology Stack

### Frontend
- React
- JavaScript
- Vite

### Backend
- Python
- Django
- Django REST Framework
- MySQL
- Redis
- Celery

### External Services
- OpenAI API
- NAVER CLOVA
- Google Cloud Text-to-Speech
- AWS S3
- Gmail SMTP

### DevOps (Planned)
- Git
- GitHub
- Docker
- Docker Hub
- Jenkins
- Kubernetes

## Repository Structure

    DearVoice-OSS/
    ├── frontend/
    │   └── dearvoice/
    ├── backend/
    ├── .gitignore
    └── README.md

## Original Project

- [Frontend](https://github.com/SSWU-SW2025-DearVoice/SSWU-SW2025-DearVoice-FrontEnd)
- [Backend](https://github.com/SSWU-SW2025-DearVoice/SSWU-SW2025-DearVoice-BackEnd)

## Security

API keys, passwords, private keys, and other credentials
must not be committed to this repository.
