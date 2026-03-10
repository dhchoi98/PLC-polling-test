#!/bin/bash
# init-labels.sh — GitHub 라벨 일괄 생성
# 사용법: ./init-labels.sh
# 사전조건: gh auth login 완료, 리포에 push 완료

set -e

REPO=$(gh repo view --json nameWithOwner -q '.nameWithOwner' 2>/dev/null)
if [ -z "$REPO" ]; then
    echo "Error: GitHub 리포를 찾을 수 없습니다. 먼저 git remote를 설정하세요."
    exit 1
fi

echo "=== GitHub 라벨 생성: $REPO ==="

# 기존 기본 라벨은 유지하고 추가 라벨만 생성
declare -A LABELS=(
    # 타입
    ["enhancement"]="#a2eeef:기능 요청"
    ["bug"]="#d73a4a:버그"
    ["task"]="#0075ca:개발 태스크"
    ["triage"]="#e4e669:분류 대기"
    ["refactor"]="#d876e3:리팩토링"
    ["test"]="#bfd4f2:테스트"
    ["docs"]="#0e8a16:문서"
    ["chore"]="#ededed:설정/빌드"
    ["perf"]="#ff9f1c:성능 개선"
    ["stale"]="#cccccc:장기 미활동"

    # 상태
    ["blocked"]="#b60205:차단됨"
    ["in progress"]="#1d76db:작업 중"

    # 우선순위
    ["priority:high"]="#ff0000:높은 우선순위"
    ["priority:medium"]="#ff9f1c:중간 우선순위"
    ["priority:low"]="#fbca04:낮은 우선순위"

    # 컴포넌트
    ["engine"]="#1d76db:엔진"
    ["frontend"]="#d4c5f9:프론트엔드"
    ["backend"]="#f9d0c4:백엔드"
    ["infra"]="#c5def5:인프라"
    ["db"]="#fbca04:데이터베이스"
)

for label in "${!LABELS[@]}"; do
    IFS=':' read -r color desc <<< "${LABELS[$label]}"
    echo "  Creating: $label ($color) — $desc"
    gh label create "$label" --color "${color#\#}" --description "$desc" --force 2>/dev/null || true
done

echo ""
echo "=== 라벨 생성 완료! ==="
echo "확인: gh label list"
