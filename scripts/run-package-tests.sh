#!/usr/bin/env bash
# 在 docker compose test-runner 容器内执行单个 lush-* 包的 pytest.
set -euo pipefail

PKG="${1:?usage: run-package-tests.sh <package-dir> [pytest args...]}"
shift || true

PKG_DIR="/workspace/$PKG"
if [[ ! -d "$PKG_DIR" ]]; then
  echo "error: package directory not found: $PKG_DIR" >&2
  exit 2
fi

# 非 root 用户在容器内可能没有 $HOME.
export HOME="${HOME:-/tmp}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-/tmp/.cache}"
mkdir -p "$XDG_CACHE_HOME"

cd "$PKG_DIR"

if [[ -d src ]]; then
  export PYTHONPATH="$(pwd)/src${PYTHONPATH:+:$PYTHONPATH}"
fi

if [[ -x .venv/bin/python ]]; then
  PY=".venv/bin/python"
elif [[ -x .venv/bin/python3 ]]; then
  PY=".venv/bin/python3"
else
  echo "error: [$PKG] missing .venv — run on host: just prepare" >&2
  exit 2
fi

if ! "$PY" -c "import pytest" 2>/dev/null; then
  echo "error: [$PKG] .venv has no pytest — re-run: just sync-all" >&2
  exit 2
fi

echo ">> [$PKG] pytest via $PY"
exec "$PY" -m pytest "$@"
