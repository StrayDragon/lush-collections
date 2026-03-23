set shell := ["bash", "-euo", "pipefail", "-c"]

# Root `justfile`: 只做“转发/批量执行”.
# 具体命令含义、参数和默认值都放在各包目录的 `justfile` 里,避免重复维护.
# 命名约定:
# - `lock/sync/test/...`         : 批量遍历所有包并执行
# - `*-one <pkg> [...]`          : 只对单个包转发执行(避免手动 cd)
# - 版本相关只提供单包命令,避免误改其它包

# `pkg_glob`: 当前仓库中“包目录”的匹配模式.
pkg_glob := "lush-*"

_default:
  @just --list

# 列出当前仓库中所有包目录 (排序后输出).
packages:
  @ls -1d {{pkg_glob}} | sort

# 以下命令会遍历每个包目录,转发执行包内 `justfile` 的同名 recipe.

# 生成/更新每个包的 `uv.lock`.
lock:
  @for d in $(ls -1d {{pkg_glob}} | sort); do echo "== lock $d"; (cd "$d" && just lock); done

# 按 `uv.lock` 同步每个包的虚拟环境(不会改锁文件).
sync:
  @for d in $(ls -1d {{pkg_glob}} | sort); do echo "== sync $d"; (cd "$d" && just sync); done

# 跑每个包的测试.
test:
  @for d in $(ls -1d {{pkg_glob}} | sort); do echo "== test $d"; (cd "$d" && just test); done

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

# Lint 并自动修复可修复项(ruff check --fix).
lint-fix:
  @for d in $(ls -1d {{pkg_glob}} | sort); do echo "== lint-fix $d"; (cd "$d" && just lint-fix); done

# 单包转发(适合在 root 里调用,避免手动 cd).
lock-one pkg:
  @cd {{pkg}} && just lock

sync-one pkg:
  @cd {{pkg}} && just sync

test-one pkg:
  @cd {{pkg}} && just test

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
