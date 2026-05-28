# lush-collections — SSOT (Agent + Repo Conventions)

> 本文件是 monorepo 演进的唯一事实源. 具体包的业务细节见各子模块 AGENTS.md.

子模块文档:
- @lush-dal-protocol/AGENTS.md
- @lush-sqlalchemyx/AGENTS.md

## Commit Convention

- 使用 conventional commits: `<type>: <subject>`.
- subject 首字母**小写**, 句末不加句号.
- type 参考: `feat`, `fix`, `refactor`, `bump`, `docs`, `test`, `dev`, `revert`.
- **不在消息体中**列举具体文件或行号 — diff 已有.

- **bump commit**: `lush-<pkg>: bump version to <ver>` (独立提交, 含 pyproject.toml 版本号变更 + 升级文档).

## Upgrade Docs

- **每次 minor/major (破坏性) 发布** 须在 `docs/upgrade/<pkg>/<from>-to-<to>.md` 记录升级指南.
- 指南包含: 版本变更表、破坏性变更及迁移步骤、问题修复说明、降级/回退方式.
- 非破坏性修复 (patch) 视严重程度可选记录.

## Upgrade Policy

- 迭代/重构时 **不做兼容**, 除非用户明确要求.
- 一步到位升级到新写法, 不保留旧路径.

## Testing & Coverage

### 覆盖率要求

- **除 `lush-wecom` 外**: 100% branch coverage, `--cov-fail-under=100`.
- **`lush-wecom`**: 豁免 100%, 仅维护纯函数/模型单测.
- `pragma: no cover` 仅用于 coverage.py 已知计量缺陷 (如异步协程边界)、防御性 unreachable 分支; **不得跳过可测逻辑**.
- 新增 `[tool.coverage.run].omit` 条目前须在对应子模块 AGENTS.md 中记录理由.

### 外部依赖

- 需要外部服务 (Redis/MySQL) 的测试须: Docker auto-up/down, 幂等, 随机命名空间, 优先本地镜像.
- CI 固定镜像: `LUSH_TEST_REDIS_IMAGE=redis:7.4-alpine`, `LUSH_TEST_MYSQL_IMAGE=mysql:8.0.40-debian`.

### Mock 策略

- 优先 **真实行为** (真代码路径 + Docker 依赖), 避免 `unittest.mock`.
- 仅允许最小 test double 覆盖: 不可达分支、可选依赖导入分支、罕见错误路径.
- 例外: `lush-sentryx` 可用 monkeypatch/dummy 覆盖可选集成.

### 一致性测试套件

- `lush-dal-protocol` 提供 `lush_dal_protocol.protocols.api_contracts` 一致性测试 mixin.
- 所有 DAL 实现包 **必须** 继承并运行该套件.

## CI / Publishing

- `.github/workflows/publish-pypi.yaml` — tag 模式 `lush-*-v*`, 所有包共用.
- 新包上线 PyPI 前须手动配置 Trusted Publisher (GitHub Actions OIDC).
- CI 使用固定 Docker 镜像 (不允许 floating tag).

## Release

- 一包一提交一标签: commit `lush-<pkg>: bump version to <ver>`, tag `lush-<pkg>-v<ver>`.
- 用 `git push origin <tag>` 逐个推送, 不依赖 `--follow-tags`.
- 用 `just release-patch` 完成: bump → test → tag → push → watch CI.

## Local Development

- 每包有 `justfile` (lock/sync/test/build/clean/fmt/lint/bump 等).
- 根 `justfile` 提供批量 (`just test`) 和单包 (`just test-one <pkg>`) 两种模式.
- 提交前运行 `just test` 或 `just test-one <pkg>` 确保覆盖率通过.
- 包间本地依赖用 `[tool.uv.sources] path = "../<pkg>"`, 发布时自动忽略.

## Docstring 规范

- 所有 library 源码 (非测试) 的 module/class/function docstring 使用 **中文**.
