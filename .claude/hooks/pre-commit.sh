#!/bin/bash
# pre-commit hook: 코드 품질 자동 검사
# Claude Code가 커밋 전에 자동으로 실행한다.

set -e

echo "[Hook] 코드 품질 검사 시작..."

ERRORS=0

# 1. Python 파일 상단 docstring 체크
echo "  파일 상단 docstring 검사..."
for file in $(git diff --cached --name-only --diff-filter=ACM | grep '\.py$'); do
    if [[ "$file" == *"__init__.py" ]] || [[ "$file" == *"conftest.py" ]]; then
        continue
    fi
    FIRST_CONTENT=$(grep -m1 -v '^$\|^#\|^from __future__' "$file" 2>/dev/null || true)
    if [[ ! "$FIRST_CONTENT" == '"""'* ]] && [[ ! "$FIRST_CONTENT" == "'''"* ]]; then
        echo "    FAIL $file — 파일 상단에 docstring이 없습니다"
        ERRORS=$((ERRORS + 1))
    fi
done

# 2. TypeScript/TSX 파일 상단 JSDoc 체크
echo "  TypeScript JSDoc 검사..."
for file in $(git diff --cached --name-only --diff-filter=ACM | grep -E '\.(ts|tsx)$'); do
    FIRST_CONTENT=$(head -5 "$file" | grep -c '/\*\*' || true)
    if [ "$FIRST_CONTENT" -eq 0 ]; then
        echo "    FAIL $file — 파일 상단에 JSDoc이 없습니다"
        ERRORS=$((ERRORS + 1))
    fi
done

# 3. 위험한 DB 명령어 체크
echo "  위험한 DB 명령어 검사..."
for file in $(git diff --cached --name-only --diff-filter=ACM | grep '\.py$'); do
    if grep -inE '(DROP TABLE|TRUNCATE|DELETE FROM [a-z_]+ *$|DELETE FROM [a-z_]+ *;)' "$file" 2>/dev/null; then
        echo "    FAIL $file — 위험한 DB 명령어가 감지되었습니다"
        ERRORS=$((ERRORS + 1))
    fi
done

# 4. 하드코딩된 API 키 패턴 체크
echo "  하드코딩 API 키 검사..."
for file in $(git diff --cached --name-only --diff-filter=ACM | grep -E '\.(py|ts|tsx|js)$'); do
    if grep -inE '(api_key|secret|password|token)\s*=\s*["\x27][A-Za-z0-9]{8,}' "$file" 2>/dev/null; then
        echo "    FAIL $file — 하드코딩된 API 키/시크릿 의심"
        ERRORS=$((ERRORS + 1))
    fi
done

# 5. Python ruff 체크
if command -v ruff &> /dev/null; then
    echo "  Ruff lint 검사..."
    PYTHON_FILES=$(git diff --cached --name-only --diff-filter=ACM | grep '\.py$' || true)
    if [ -n "$PYTHON_FILES" ]; then
        ruff check $PYTHON_FILES || ERRORS=$((ERRORS + 1))
    fi
fi

# 결과
echo ""
if [ $ERRORS -gt 0 ]; then
    echo "FAIL 검사 실패: $ERRORS 건의 문제 발견"
    exit 1
else
    echo "PASS 모든 검사 통과"
    exit 0
fi
