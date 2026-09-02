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

_venv_python() {
  if [[ -x .venv/bin/python ]]; then
    echo ".venv/bin/python"
  elif [[ -x .venv/bin/python3 ]]; then
    echo ".venv/bin/python3"
  fi
}

PY="$(_venv_python || true)"
if [[ -z "$PY" ]] || ! "$PY" -c "import pytest" 2>/dev/null; then
  echo ">> [$PKG] syncing .venv in container (host venv missing or not usable)"
  export UV_LINK_MODE="${UV_LINK_MODE:-copy}"
  uv sync -p 3.10 --frozen --default-index https://pypi.org/simple
  PY="$(_venv_python || true)"
fi

if [[ -z "$PY" ]]; then
  echo "error: [$PKG] missing .venv after sync — check path deps and uv lock" >&2
  exit 2
fi

if ! "$PY" -c "import pytest" 2>/dev/null; then
  echo "error: [$PKG] .venv has no pytest after sync" >&2
  exit 2
fi

echo ">> [$PKG] pytest via $PY"
exec "$PY" -m pytest "$@"
