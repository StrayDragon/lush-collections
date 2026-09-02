#!/usr/bin/env bash
# 在 compose bridge 内顺序跑所有 lush-* 测试.
# 依赖服务由 docker compose run 的 depends_on 自动拉起, 无需手动 test-infra-up.
#
# 环境变量:
#   LUSH_TEST_TEARDOWN=1  全部跑完后 docker compose down (默认保留 infra 便于重复跑)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT/docker-compose.test.yml}"
TEARDOWN="${LUSH_TEST_TEARDOWN:-0}"

cleanup() {
  if [[ "$TEARDOWN" == "1" ]]; then
    docker compose -f "$COMPOSE_FILE" down --remove-orphans
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
  docker compose -f "$COMPOSE_FILE" --profile test run --rm test-runner "$pkg"
done
