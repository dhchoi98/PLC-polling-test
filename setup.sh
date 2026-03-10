#!/bin/bash
# setup.sh — 템플릿 초기화 스크립트
# 사용법: ./setup.sh <project-name> <github-username>
# 예시:   ./setup.sh my-awesome-app dhchoi98

set -e

PROJECT_NAME="${1:?Usage: ./setup.sh <project-name> <github-username>}"
GITHUB_USER="${2:?Usage: ./setup.sh <project-name> <github-username>}"
PROJECT_DESC="${3:-$PROJECT_NAME}"

echo "=== Claude Project Template Setup ==="
echo "  Project:  $PROJECT_NAME"
echo "  User:     $GITHUB_USER"
echo "  Desc:     $PROJECT_DESC"
echo ""

# 1. 플레이스홀더 치환
echo "[1/5] 플레이스홀더 치환..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    SED_CMD="sed -i ''"
else
    SED_CMD="sed -i"
fi

find . -type f \( -name "*.md" -o -name "*.yml" -o -name "*.yaml" -o -name "*.json" -o -name "*.sh" \) \
    ! -path "./.git/*" \
    ! -path "./setup.sh" \
    -exec $SED_CMD "s/{{PROJECT_NAME}}/$PROJECT_NAME/g" {} +

find . -type f \( -name "*.md" -o -name "*.yml" -o -name "*.yaml" -o -name "*.json" -o -name "*.sh" \) \
    ! -path "./.git/*" \
    ! -path "./setup.sh" \
    -exec $SED_CMD "s/{{GITHUB_USER}}/$GITHUB_USER/g" {} +

find . -type f \( -name "*.md" -o -name "*.yml" -o -name "*.yaml" -o -name "*.json" -o -name "*.sh" \) \
    ! -path "./.git/*" \
    ! -path "./setup.sh" \
    -exec $SED_CMD "s/{{PROJECT_DESCRIPTION}}/$PROJECT_DESC/g" {} +

# macOS sed 백업 파일 정리
find . -name "*''" -delete 2>/dev/null || true

# 2. ISSUE_TEMPLATE config에 프로젝트 링크 추가
echo "[2/5] 이슈 템플릿 설정..."
cat > .github/ISSUE_TEMPLATE/config.yml << EOF
blank_issues_enabled: false
contact_links:
  - name: PLAN.md
    url: https://github.com/$GITHUB_USER/$PROJECT_NAME/blob/main/PLAN.md
    about: 전체 개발 계획 확인
EOF

# 3. hooks 실행 권한 설정
echo "[3/5] Hook 실행 권한 설정..."
chmod +x .claude/hooks/*.sh

# 4. 기본 디렉토리 생성
echo "[4/5] 프로젝트 디렉토리 생성..."
mkdir -p backend frontend shared docs

# 5. .gitignore 생성
echo "[5/5] .gitignore 생성..."
cat > .gitignore << 'GITIGNORE'
# Python
__pycache__/
*.py[cod]
*.egg-info/
.venv/
venv/
dist/
build/

# Node
node_modules/
.next/
out/

# Environment
.env
.env.local
.env.*.local

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# Claude Code local settings (사용자별 허용 목록)
.claude/settings.local.json
GITIGNORE

echo ""
echo "=== Setup 완료! ==="
echo ""
echo "다음 단계:"
echo "  1. CLAUDE.md를 프로젝트에 맞게 수정"
echo "  2. PLAN.md에 개발 계획 작성"
echo "  3. ./init-labels.sh 실행하여 GitHub 라벨 생성"
echo "  4. setup.sh와 init-labels.sh 삭제 후 첫 커밋"
echo ""
echo "  rm setup.sh init-labels.sh"
echo "  git add -A && git commit -m 'chore: 프로젝트 초기 설정'"
