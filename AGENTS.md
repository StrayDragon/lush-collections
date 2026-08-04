# lush-collections — SSOT (Agent + Repo Conventions)

> 本文件是 monorepo 演进的唯一事实源. 具体包的业务细节见各子模块 AGENTS.md.

子模块文档:
- @lush-dal-protocol/AGENTS.md
- @lush-sqlalchemyx/AGENTS.md
- @lush-redisx/AGENTS.md
- @lush-stdx/AGENTS.md
- @lush-pydanticx/AGENTS.md
- @lush-fastapix/AGENTS.md
- @lush-logx/AGENTS.md
- @lush-sentryx-core/AGENTS.md
- @lush-sentryx/AGENTS.md
- @lush-wecom/AGENTS.md
- @lush-exp/AGENTS.md

## Commit Convention

- 使用 conventional commits: `<type>: <subject>`.
- subject 首字母**小写**, 句末不加句号.
- type 参考: `feat`, `fix`, `refactor`, `bump`, `docs`, `test`, `dev`, `revert`.
- **不在消息体中**列举具体文件或行号 — diff 已有.

- **bump commit**: `lush-<pkg>: bump version to <ver>` (独立提交, 含 pyproject.toml 版本号变更 + 升级文档).

## Changelog

- 每个子包维护自己的 `CHANGELOG.md` (位于包根目录).
- **每次 minor/major (破坏性) 发布** 须在 `CHANGELOG.md` 记录破坏性变更和重要变更.
- 记录内容: 破坏性变更 (Breaking Changes) + 重要变更 (Changes).
- 非破坏性修复 (patch) 不记录.
- 格式参考: [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/).

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
- CI 固定镜像: `LUSH_TEST_REDIS_IMAGE=redis:7.4-alpine`, `LUSH_TEST_MYSQL_IMAGE=mysql:8.0.40-debian`,
  matrix 另含 `mysql:5.7` (勿用浮动 `mysql:8`, 当前指向 8.4 且已移除 `mysql_native_password`).

### Mock 策略

- 优先 **真实行为** (真代码路径 + Docker 依赖), 避免 `unittest.mock`.
- 仅允许最小 test double 覆盖: 不可达分支、可选依赖导入分支、罕见错误路径.
- 例外: `lush-sentryx` 可用 monkeypatch/dummy 覆盖可选集成.

### 一致性测试套件

- 一致性测试 mixin 位于 `lush_dal_protocol.testing` (`conformance` / `dto_conformance`), 下游 DAL 实现包 **必须** 继承并运行该套件.

## CI / Publishing

- `.github/workflows/publish-pypi.yaml` — tag 模式 `lush-*-v*`, 所有包共用.
- 新包上线 PyPI 前须手动配置 Trusted Publisher (GitHub Actions OIDC).
- CI 使用固定 Docker 镜像 (不允许 floating tag).

## Release

- 一包一提交一标签: commit `lush-<pkg>: bump version to <ver>`, tag `lush-<pkg>-v<ver>`.
- 用 `git push origin <tag>` 逐个推送, 不依赖 `--follow-tags`.
- 用 `just release-patch` 完成: bump → test → tag → push → watch CI.

### Tag / 发版门禁 (强制)

- **创建 git tag、推送 tag、执行 `just release-*` 等会触发 PyPI 发布的操作, 必须先获得用户明确同意.**
- Agent **不得**在未获同意时主动 `git tag` / `git push <tag>` / 运行 release recipe.
- bump commit、文档与代码改动可以先行准备; **发版动作 (tag + push tag) 单独征求确认后再执行.**
- 理由: tag 会触发 `.github/workflows/publish-pypi.yaml`, 属于不可逆的对外发版.

## Local Development

- 每包有 `justfile` (lock/sync/test/build/clean/fmt/lint/bump 等).
- 根 `justfile` 提供批量 (`just test`) 和单包 (`just test-one <pkg>`) 两种模式.
- 提交前运行 `just test` 或 `just test-one <pkg>` 确保覆盖率通过.
- 包间本地依赖用 `[tool.uv.sources] path = "../<pkg>"`, 发布时自动忽略.

## Docstring 规范

- 所有 library 源码 (非测试) 的 module/class/function docstring 使用 **中文**.
