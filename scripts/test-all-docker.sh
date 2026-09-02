#!/usr/bin/env bash
# 在 compose bridge 内顺序跑所有 lush-* 测试.
# 各包按需启用 redis/mysql profile (见 scripts/compose-test-run.sh).
#
# 环境变量:
#   LUSH_TEST_TEARDOWN=1  全部跑完后 docker compose down (默认保留 infra 便于重复跑)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT/docker-compose.test.yml}"
TEARDOWN="${LUSH_TEST_TEARDOWN:-0}"

cleanup() {
  if [[ "$TEARDOWN" == "1" ]]; then
    docker compose -f "$COMPOSE_FILE" --profile redis --profile mysql --profile test down --remove-orphans
  fi
}
trap cleanup EXIT

cd "$ROOT"

export LOCAL_UID="${LOCAL_UID:-$(id -u)}"
export LOCAL_GID="${LOCAL_GID:-$(id -g)}"
export HOME="${HOME:?HOME must be set}"

for pkg in $(ls -1d lush-* | sort); do
  [[ -d "$pkg" ]] || continue
  echo "== test-docker $pkg"
  ./scripts/compose-test-run.sh "$pkg"
done
