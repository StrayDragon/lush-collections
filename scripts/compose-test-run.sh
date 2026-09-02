#!/usr/bin/env bash
# 以当前宿主机用户身份运行 test-runner (避免 root 创建 .venv 导致权限问题).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT/docker-compose.test.yml}"

export LOCAL_UID="${LOCAL_UID:-$(id -u)}"
export LOCAL_GID="${LOCAL_GID:-$(id -g)}"
export HOME="${HOME:?HOME must be set}"

exec docker compose -f "$COMPOSE_FILE" --profile test run --rm test-runner "$@"
