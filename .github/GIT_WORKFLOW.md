# Git Workflow & GitHub 관리 규칙

> Claude Code가 브랜치, 이슈, PR을 자동 관리할 때 따르는 규칙.

## 브랜치 전략 (1인 개발 최적화 Git-flow)

```
main                                    ← 제품 출시 브랜치 (직접 push 금지)
  └── develop (기본 브랜치)               ← 일상 개발 (소형 작업은 직접 커밋)
       ├── dev/feat/{name}                ← 중형 이상 기능 개발
       ├── dev/fix/{name}                 ← 중형 이상 버그 수정
       └── dev/refactor/{name}            ← 중형 이상 리팩토링
  └── hotfix/{name}                       ← 긴급 버그 수정 (main에서 분기)
```

### 작업 규모별 방식

| 규모 | 기준 | 방식 | 예시 |
|------|------|------|------|
| 소형 | 커밋 1~2개 | `develop`에 직접 커밋+push | docs 수정, 설정 변경, 오타 |
| 중형 | 커밋 3개+ | 브랜치 → 이슈 → PR → squash merge | 기능 구현, API, UI 페이지 |
| 긴급 | 크리티컬 버그 | `hotfix/{name}` → main + develop | 인증 실패, 데이터 유실 |

## 커밋 메시지

```
<type>: <subject>
```

| type | 용도 |
|------|------|
| feat | 새 기능 |
| fix | 버그 수정 |
| docs | 문서 |
| style | 포맷팅 (동작 변경 없음) |
| refactor | 리팩토링 |
| test | 테스트 |
| chore | 빌드, 설정 |
| perf | 성능 개선 |

- Breaking Change: 제목에 `!` 추가, body에 설명 필수
- footer: `closes #123`으로 이슈 자동 닫기

## 이슈 관리

1. 담당자(Assignees) 반드시 지정
2. Task list (`- [ ]`) 적극 활용
3. 라벨 부여 (타입 + 컴포넌트)

## PR 관리

- PR 제목: `[#이슈번호] 변경 사항`
- squash merge 사용
- 머지 후 원격 브랜치 삭제
- `main` ← `develop` 머지만 merge commit 사용

## 라벨

| 라벨 | 색상 | 용도 |
|------|------|------|
| `bug` | #d73a4a | 버그 |
| `enhancement` | #a2eeef | 기능 요청 |
| `task` | #0075ca | 개발 태스크 |
| `triage` | #e4e669 | 분류 대기 |
| `refactor` | #d876e3 | 리팩토링 |
| `test` | #bfd4f2 | 테스트 |
| `docs` | #0e8a16 | 문서 |
| `chore` | #ededed | 설정/빌드 |
| `perf` | #ff9f1c | 성능 개선 |
| `stale` | #cccccc | 장기 미활동 |
| `blocked` | #b60205 | 차단됨 |
| `in progress` | #1d76db | 작업 중 |
| `priority:high` | #ff0000 | 높은 우선순위 |
| `priority:medium` | #ff9f1c | 중간 우선순위 |
| `priority:low` | #fbca04 | 낮은 우선순위 |
| `engine` | #1d76db | 엔진 |
| `frontend` | #d4c5f9 | 프론트엔드 |
| `backend` | #f9d0c4 | 백엔드 |
| `infra` | #c5def5 | 인프라 |
| `db` | #fbca04 | 데이터베이스 |
