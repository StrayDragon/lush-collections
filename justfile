set shell := ["bash", "-euo", "pipefail", "-c"]

# Root `justfile`: 只做“转发/批量执行”.
# 具体命令含义、参数和默认值都放在各包目录的 `justfile` 里,避免重复维护.
# 命名约定:
# - `lock/sync/test/...`         : 批量遍历所有包并执行
# - `*-one <pkg> [...]`          : 只对单个包转发执行(避免手动 cd)
# - 版本相关只提供单包命令,避免误改其它包

# `pkg_glob`: 当前仓库中“包目录”的匹配模式.
pkg_glob := "lush-*"

# compose 测试基础设施 (bridge 内网, 不映射宿主机端口).
compose_file := "docker-compose.test.yml"

_default:
  @just --list

# 列出当前仓库中所有包目录 (排序后输出, 排除 lush-versions.toml 等文件).
packages:
  #!/usr/bin/env bash
  for d in {{pkg_glob}}; do
    [[ -d "$d" ]] && echo "${d%/}"
  done | sort

# 以下命令会遍历每个包目录,转发执行包内 `justfile` 的同名 recipe.

# 生成/更新每个包的 `uv.lock`.
lock:
  @just packages | while read -r d; do echo "== lock $d"; (cd "$d" && just lock); done

# 按 `uv.lock` 同步每个包的虚拟环境(不会改锁文件).
sync:
  @just packages | while read -r d; do echo "== sync $d"; (cd "$d" && just sync); done

# 宿主机一次性准备 (test-docker 前置; 网络/代理由环境变量自行配置).
prepare:
  @just lock
  @just sync
  @echo "prepare done — run: just test-all-docker"

# 跑每个包的测试 (lush-redisx / lush-sqlalchemyx 自动走 compose bridge).
test:
  #!/usr/bin/env bash
  set -euo pipefail
  mapfile -t _pkgs < <(just packages)
  for d in "${_pkgs[@]}"; do
    case "$d" in
      lush-redisx|lush-sqlalchemyx)
        echo "== test-docker $d"
        just test-docker "$d"
        ;;
      *)
        echo "== test $d"
        (cd "$d" && just test)
        ;;
    esac
  done

# 启动 compose 测试基础设施 (redis + mysql57 + mysql8, 无宿主机端口映射).
# 通常不需要手动调用: ``just test-docker`` 会通过 depends_on 自动拉起依赖.
test-infra-up:
  @docker compose -f {{compose_file}} --profile redis --profile mysql up -d --wait redis mysql57 mysql8

# 停止 compose 测试基础设施 (释放内存/容器; 日常跑测可不调).
test-infra-down:
  @docker compose -f {{compose_file}} --profile redis --profile mysql --profile test down --remove-orphans

# 在 compose bridge 内跑单个包测试 (一条命令, 自动起依赖, 不占用本机 6379/3306).
test-docker pkg *pytest_args:
  @./scripts/compose-test-run.sh {{pkg}} {{pytest_args}}

# 在 compose bridge 内跑所有包测试 (LUSH_TEST_TEARDOWN=1 跑完自动 down).
test-all-docker:
  #!/usr/bin/env bash
  set -euo pipefail
  missing=()
  while read -r d; do
    [[ -x "$d/.venv/bin/python" || -x "$d/.venv/bin/python3" ]] || missing+=("$d")
  done < <(just packages)
  if ((${#missing[@]})); then
    echo "error: missing .venv in: ${missing[*]}" >&2
    echo "run first: just prepare" >&2
    exit 2
  fi
  LUSH_TEST_TEARDOWN="${LUSH_TEST_TEARDOWN:-0}" ./scripts/test-all-docker.sh

# 构建 test-runner 镜像 (修改 Dockerfile.test 后执行).
test-docker-build:
  @docker compose -f {{compose_file}} --profile test build test-runner

# 删除 test-docker 以 root 创建的 .venv (需 sudo).
clean-docker-venvs:
  #!/usr/bin/env bash
  set -euo pipefail
  found=0
  while read -r d; do
    venv="$d/.venv"
    [[ -d "$venv" ]] || continue
    if [[ "$(stat -c '%U' "$venv")" == "root" ]]; then
      echo "== removing root-owned $venv"
      sudo rm -rf "$venv"
      found=1
    fi
  done < <(just packages)
  [[ "$found" -eq 1 ]] || echo "no root-owned .venv found"

# 构建每个包的 dist (wheel/sdist).
build:
  @for d in $(ls -1d {{pkg_glob}} | sort); do echo "== build $d"; (cd "$d" && just build); done

# 清理每个包的缓存/构建产物.
clean:
  @for d in $(ls -1d {{pkg_glob}} | sort); do echo "== clean $d"; (cd "$d" && just clean); done

# 格式化每个包的代码(ruff format).
fmt:
  @for d in $(ls -1d {{pkg_glob}} | sort); do echo "== fmt $d"; (cd "$d" && just fmt); done

# Lint 检查(ruff check).
lint:
  @for d in $(ls -1d {{pkg_glob}} | sort); do echo "== lint $d"; (cd "$d" && just lint); done

# 质量门禁聚合: lint + 全包测试 (提交前运行, 防回归).
qa:
  @just lint
  @just test

# Lint 并自动修复可修复项(ruff check --fix).
lint-fix:
  @for d in $(ls -1d {{pkg_glob}} | sort); do echo "== lint-fix $d"; (cd "$d" && just lint-fix); done

# 单包转发(适合在 root 里调用,避免手动 cd).
lock-one pkg:
  @cd {{pkg}} && just lock

sync-one pkg:
  @cd {{pkg}} && just sync

test-one pkg:
  #!/usr/bin/env bash
  set -euo pipefail
  case "{{pkg}}" in
    lush-redisx|lush-sqlalchemyx)
      just test-docker "{{pkg}}"
      ;;
    *)
      cd "{{pkg}}" && just test
      ;;
  esac

build-one pkg:
  @cd {{pkg}} && just build

clean-one pkg:
  @cd {{pkg}} && just clean

fmt-one pkg:
  @cd {{pkg}} && just fmt

lint-one pkg:
  @cd {{pkg}} && just lint

lint-fix-one pkg:
  @cd {{pkg}} && just lint-fix

# 版本管理: 每个包独立维护版本号 (对应各自 `pyproject.toml`).
version-one pkg:
  @cd {{pkg}} && just version

# 显式设置版本号 (不触发重新 lock; 需要的话手动 `just lock-one <pkg>`).
set-version-one pkg version:
  @cd {{pkg}} && just set-version {{version}}

# 语义化 bump (level: major/minor/patch/alpha/beta/rc/dev/post...).
bump-one pkg level:
  @cd {{pkg}} && just bump {{level}}

# 多包 bump 快捷方式:
# - 直接传包名: `just bump-patch lush-stdx lush-redisx`
# - 不传包名: 使用 `fzf -m` 交互多选

bump-major *pkgs:
  #!/usr/bin/env bash
  set -euo pipefail

  pkgs="{{pkgs}}"
  if [ -z "$pkgs" ]; then
    pkgs="$(just packages | fzf -m --prompt='packages> ')" || exit 0
  fi

  for d in $pkgs; do
    echo "== bump major $d"
    (cd "$d" && just bump major)
  done

bump-minor *pkgs:
  #!/usr/bin/env bash
  set -euo pipefail

  pkgs="{{pkgs}}"
  if [ -z "$pkgs" ]; then
    pkgs="$(just packages | fzf -m --prompt='packages> ')" || exit 0
  fi

  for d in $pkgs; do
    echo "== bump minor $d"
    (cd "$d" && just bump minor)
  done

bump-patch *pkgs:
  #!/usr/bin/env bash
  set -euo pipefail

  pkgs="{{pkgs}}"
  if [ -z "$pkgs" ]; then
    pkgs="$(just packages | fzf -m --prompt='packages> ')" || exit 0
  fi

  for d in $pkgs; do
    echo "== bump patch $d"
    (cd "$d" && just bump patch)
  done

# Release helper:
# - Patch-bump each package (one commit per package)
# - Create tag `lush-<pkg>-v<ver>` (one tag per package)
# - Push main, then push tags one-by-one (reliably triggers tag workflows)
# - Optionally watch the publish workflow to complete
#
# Env knobs:
# - RELEASE_REMOTE=origin
# - RELEASE_WORKFLOW=publish-pypi.yaml
# - RELEASE_SKIP_TESTS=1    (skip local `just test-one <pkg>`)
# - RELEASE_WATCH=0         (don't wait for GH Actions)
release-patch *pkgs:
  #!/usr/bin/env bash
  set -euo pipefail

  remote="${RELEASE_REMOTE:-origin}"
  workflow="${RELEASE_WORKFLOW:-publish-pypi.yaml}"
  skip_tests="${RELEASE_SKIP_TESTS:-0}"
  watch="${RELEASE_WATCH:-1}"

  if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "error: working tree is not clean" >&2
    exit 2
  fi

  branch="$(git rev-parse --abbrev-ref HEAD)"
  if [ "$branch" != "main" ]; then
    echo "error: must run on branch 'main' (current: $branch)" >&2
    exit 2
  fi

  if ! command -v gh >/dev/null 2>&1; then
    echo "error: missing dependency: gh (GitHub CLI)" >&2
    exit 2
  fi
  gh auth status -h github.com >/dev/null

  pkgs="{{pkgs}}"
  if [ -z "$pkgs" ]; then
    pkgs="$(just packages | fzf -m --prompt='release> ')" || exit 0
  fi

  # Create one commit + one tag per package.
  tags=()
  for pkg in $pkgs; do
    if [ ! -f "$pkg/pyproject.toml" ]; then
      echo "error: package not found or missing pyproject.toml: $pkg" >&2
      exit 2
    fi

    echo "== bump patch $pkg"
    just bump-one "$pkg" patch
    version="$(cd "$pkg" && uv version --short)"

    if [ "$skip_tests" != "1" ]; then
      echo "== test $pkg"
      just test-one "$pkg"
    fi

    git add "$pkg/pyproject.toml"
    git commit -m "$pkg: bump version to $version"

    tag="$pkg-v$version"
    if git rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
      echo "error: local tag already exists: $tag" >&2
      exit 2
    fi
    if git ls-remote --tags "$remote" "$tag" | rg -q "refs/tags/$tag$"; then
      echo "error: remote tag already exists: $tag" >&2
      exit 2
    fi

    git tag -a "$tag" -m "$pkg v$version"
    tags+=("$tag")
  done

  echo "== push branch: main"
  git push "$remote" main

  # Push tags one-by-one (more reliable than `--follow-tags` for triggering tag workflows).
  for tag in "${tags[@]}"; do
    echo "== push tag $tag"
    git push "$remote" "$tag"

    if [ "$watch" != "1" ]; then
      continue
    fi

    echo "== watch workflow ($workflow) for $tag"
    run_id=""
    for _ in $(seq 1 60); do
      run_id="$(
        gh run list \
          --workflow "$workflow" \
          --event push \
          --branch "$tag" \
          --limit 1 \
          --json databaseId \
          --jq '.[0].databaseId // empty'
      )"
      if [ -n "$run_id" ]; then
        break
      fi
      sleep 2
    done
    if [ -z "$run_id" ]; then
      echo "error: workflow run not found for tag: $tag" >&2
      exit 3
    fi
    gh run watch "$run_id" --exit-status
  done
