#!/bin/bash
# lint hook: Python 코드 자동 포맷팅 및 타입 체크

set -e

TARGET=${1:-.}

echo "[Hook] Lint & Format..."

# Ruff format
if command -v ruff &> /dev/null; then
    echo "  Ruff format..."
    ruff format "$TARGET" --quiet
    echo "  Ruff check..."
    ruff check "$TARGET" --fix --quiet
fi

# MyPy (backend만)
if command -v mypy &> /dev/null && [[ "$TARGET" == *"backend"* ]]; then
    echo "  MyPy type check..."
    mypy "$TARGET" --ignore-missing-imports --quiet || true
fi

echo "Lint 완료"
