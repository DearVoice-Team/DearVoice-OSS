# DearVoice-OSS 협업 규칙

## Branch 전략

| 브랜치 | 용도 |
|--------|------|
| `main` | 최종 배포 브랜치 |
| `develop` | 개발 통합 브랜치 |
| `feature/이슈번호-작업내용` | 새 기능 구현 |
| `fix/이슈번호-작업내용` | 버그 수정 |
| `docs/이슈번호-작업내용` | 문서 작업 |
| `chore/이슈번호-작업내용` | 설정, 패키지, 환경 변경 |
| `test/이슈번호-작업내용` | 테스트 코드 |
| `ci/이슈번호-작업내용` | CI/CD 설정 |
| `refactor/이슈번호-작업내용` | 리팩토링 |

> 모든 작업 브랜치는 `develop`에서 분기하고 `develop`으로 PR합니다.

---

## Commit Convention

```
type: 작업 내용
```

| type | 사용 시점 |
|------|----------|
| `feat` | 새로운 기능 추가 |
| `fix` | 버그 수정 |
| `docs` | 문서 수정 |
| `chore` | 설정 파일, 패키지 변경 |
| `refactor` | 기능 변화 없는 코드 정리 |
| `test` | 테스트 코드 추가/수정 |
| `ci` | CI/CD 설정 변경 |

**예시**
```
feat: 음성 편지 녹음 기능 추가
fix: 로그인 토큰 만료 오류 수정
docs: README 실행 방법 업데이트
ci: Jenkinsfile CI 스테이지 작성
```

---

## PR 규칙

- **제목 형식**: `[type] #이슈번호 작업 내용`
  - 예: `[feat] #12 GitHub 협업 규칙 파일 추가`
- **base 브랜치**: 항상 `develop`
- **Merge 조건**: 최소 1명 Approve 후 Merge
- **Merge 후**: 작업 브랜치 삭제
- **이슈 자동 닫기**: PR 본문에 `Closes #이슈번호` 작성

---

## Code Review 규칙

- PR 등록 후 24시간 내 리뷰
- 리뷰어는 최소 1명 이상 Approve 후 Merge
- `main` 브랜치는 2명 이상 Approve 필요

---

## 보안 주의사항

> **절대 커밋 금지**

- `.env` 파일
- API 키, 비밀번호
- GCP 서비스 계정 JSON 파일 (`*.json` 인증 파일)
- AWS 자격증명 파일

`.gitignore`에 반드시 추가하세요:
```
.env
*.json
```

---

## 작업 흐름 요약

```
1. GitHub에서 이슈 생성  →  #번호 발급
2. 브랜치 생성: git checkout -b feature/번호-작업내용
3. 작업 후 커밋: git commit -m "feat: 작업 내용"
4. Push: git push origin feature/번호-작업내용
5. PR 생성 (base: develop), 제목: [feat] #번호 작업 내용
6. 리뷰 → Approve → Merge → 브랜치 삭제
```
