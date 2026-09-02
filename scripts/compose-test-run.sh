#!/usr/bin/env bash
# 以当前宿主机用户身份运行 test-runner (避免 root 创建 .venv 导致权限问题).
# 按包名自动启用 compose profile, 无外部依赖的包不启动 redis/mysql.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT/docker-compose.test.yml}"

export LOCAL_UID="${LOCAL_UID:-$(id -u)}"
export LOCAL_GID="${LOCAL_GID:-$(id -g)}"
export HOME="${HOME:?HOME must be set}"

PKG="${1:?usage: compose-test-run.sh <package-name> [pytest args...]}"
shift || true

compose_profiles=(--profile test)
infra_services=()

case "$PKG" in
  lush-redisx)
    compose_profiles+=(--profile redis)
    infra_services=(redis)
    ;;
  lush-sqlalchemyx)
    compose_profiles+=(--profile mysql)
    infra_services=(mysql57 mysql8)
    ;;
esac

if ((${#infra_services[@]})); then
  docker compose -f "$COMPOSE_FILE" "${compose_profiles[@]}" up -d --wait "${infra_services[@]}"
fi

exec docker compose -f "$COMPOSE_FILE" "${compose_profiles[@]}" run --rm test-runner "$PKG" "$@"
