<p align="center">
  <img src="docs/assets/logo.svg" alt="lush-collections" width="160">
</p>

<h1 align="center">lush-collections</h1>

<p align="center">
  一组小而独立的 Python 包合集: 集中维护, 独立发布.
</p>

| - | - |
| --- | --- |
| 项目工具 | [![uv](https://img.shields.io/badge/uv-managed-6A2C70?logo=uv&logoColor=white&style=flat-square)](https://github.com/astral-sh/uv) [![ruff](https://img.shields.io/badge/ruff-linted-D7FF64?logo=ruff&logoColor=111111&style=flat-square)](https://github.com/astral-sh/ruff) |
| Python | [![Python](https://img.shields.io/badge/python-%3E%3D3.10-3776AB?logo=python&logoColor=white&style=flat-square)](https://www.python.org/) |

## Packages

| 包 | 分发 |
| --- | --- |
| [`lush-stdx`](./lush-stdx) | [![PyPI version](https://img.shields.io/pypi/v/lush-stdx?logo=pypi&logoColor=white&style=flat-square)](https://pypi.org/project/lush-stdx/) [![Python versions](https://img.shields.io/pypi/pyversions/lush-stdx?logo=python&logoColor=white&style=flat-square)](https://pypi.org/project/lush-stdx/) |
| [`lush-logx`](./lush-logx) | [![PyPI version](https://img.shields.io/pypi/v/lush-logx?logo=pypi&logoColor=white&style=flat-square)](https://pypi.org/project/lush-logx/) [![Python versions](https://img.shields.io/pypi/pyversions/lush-logx?logo=python&logoColor=white&style=flat-square)](https://pypi.org/project/lush-logx/) |
| [`lush-pydanticx`](./lush-pydanticx) | [![PyPI version](https://img.shields.io/pypi/v/lush-pydanticx?logo=pypi&logoColor=white&style=flat-square)](https://pypi.org/project/lush-pydanticx/) [![Python versions](https://img.shields.io/pypi/pyversions/lush-pydanticx?logo=python&logoColor=white&style=flat-square)](https://pypi.org/project/lush-pydanticx/) |
| [`lush-dal-protocol`](./lush-dal-protocol) | [![PyPI version](https://img.shields.io/pypi/v/lush-dal-protocol?logo=pypi&logoColor=white&style=flat-square)](https://pypi.org/project/lush-dal-protocol/) [![Python versions](https://img.shields.io/pypi/pyversions/lush-dal-protocol?logo=python&logoColor=white&style=flat-square)](https://pypi.org/project/lush-dal-protocol/) |
| [`lush-sqlalchemyx`](./lush-sqlalchemyx) | [![PyPI version](https://img.shields.io/pypi/v/lush-sqlalchemyx?logo=pypi&logoColor=white&style=flat-square)](https://pypi.org/project/lush-sqlalchemyx/) [![Python versions](https://img.shields.io/pypi/pyversions/lush-sqlalchemyx?logo=python&logoColor=white&style=flat-square)](https://pypi.org/project/lush-sqlalchemyx/) |
| [`lush-redisx`](./lush-redisx) | [![PyPI version](https://img.shields.io/pypi/v/lush-redisx?logo=pypi&logoColor=white&style=flat-square)](https://pypi.org/project/lush-redisx/) [![Python versions](https://img.shields.io/pypi/pyversions/lush-redisx?logo=python&logoColor=white&style=flat-square)](https://pypi.org/project/lush-redisx/) |
| [`lush-fastapix`](./lush-fastapix) | [![PyPI version](https://img.shields.io/pypi/v/lush-fastapix?logo=pypi&logoColor=white&style=flat-square)](https://pypi.org/project/lush-fastapix/) [![Python versions](https://img.shields.io/pypi/pyversions/lush-fastapix?logo=python&logoColor=white&style=flat-square)](https://pypi.org/project/lush-fastapix/) |
| [`lush-sentryx-core`](./lush-sentryx-core) | [![PyPI version](https://img.shields.io/pypi/v/lush-sentryx-core?logo=pypi&logoColor=white&style=flat-square)](https://pypi.org/project/lush-sentryx-core/) [![Python versions](https://img.shields.io/pypi/pyversions/lush-sentryx-core?logo=python&logoColor=white&style=flat-square)](https://pypi.org/project/lush-sentryx-core/) |
| [`lush-sentryx`](./lush-sentryx) | [![PyPI version](https://img.shields.io/pypi/v/lush-sentryx?logo=pypi&logoColor=white&style=flat-square)](https://pypi.org/project/lush-sentryx/) [![Python versions](https://img.shields.io/pypi/pyversions/lush-sentryx?logo=python&logoColor=white&style=flat-square)](https://pypi.org/project/lush-sentryx/) |
| [`lush-wecom`](./lush-wecom) | [![PyPI version](https://img.shields.io/pypi/v/lush-wecom?logo=pypi&logoColor=white&style=flat-square)](https://pypi.org/project/lush-wecom/) [![Python versions](https://img.shields.io/pypi/pyversions/lush-wecom?logo=python&logoColor=white&style=flat-square)](https://pypi.org/project/lush-wecom/) |
| [`lush-exp`](./lush-exp) | [![PyPI version](https://img.shields.io/pypi/v/lush-exp?logo=pypi&logoColor=white&style=flat-square)](https://pypi.org/project/lush-exp/) [![Python versions](https://img.shields.io/pypi/pyversions/lush-exp?logo=python&logoColor=white&style=flat-square)](https://pypi.org/project/lush-exp/) |

## 简介

每个 `lush-*` 目录都是一个完整的 Python 包(独立的 `pyproject.toml` / `uv.lock` / 测试),可以单独构建、单独发布.
这里没有 uv workspace 的概念,需要改哪个就进哪个目录.

## 快速开始

- Python: `>=3.10`
- 包管理: `uv`
- 可选: `just` (根目录有 `justfile`)

根目录批量跑:

```bash
just packages
just lock
just sync
just test
```

单包开发(以 `lush-redisx` 为例):

```bash
cd lush-redisx
uv lock -p 3.10 --default-index https://pypi.org/simple
uv sync -p 3.10 --frozen --default-index https://pypi.org/simple
uv run -p 3.10 pytest
```

## 仓库结构

```mermaid
flowchart TB
  Root[仓库根目录] --> RootJust[justfile（批量/转发）]
  Root --> Pkg[lush-*/（包目录）]
  Pkg --> PJ[justfile]
  Pkg --> PP[pyproject.toml]
  Pkg --> UL[uv.lock]
  Pkg --> SRC[src/]
  Pkg --> TESTS[tests/]
```

## 内部依赖联调

仓库内包之间通过各自的 `[tool.uv.sources]` 指向兄弟目录,用于本地联调.
对外依赖仍然写在 `[project].dependencies` 里(带版本下限),不用 workspace 也能正常安装.

## 版本与发布

```mermaid
flowchart LR
  Dev[开发者] --> Bump[调整版本号]
  Bump --> Tag[打 tag：pkg-vX.Y.Z]
  Tag --> Push[推送 tag]
  Push --> GA[GitHub Actions]
  GA --> Test[uv sync + pytest]
  Test --> Build[uv build]
  Build --> Publish[uv publish（Trusted Publishing）]
  Publish --> PyPI[PyPI]
```

每个包独立发版,推荐用 tag 来触发 GitHub Actions 发布:

- tag 约定: `<package>-v<version>` (例如 `lush-stdx-v0.1.1`)
- workflow: `.github/workflows/publish-pypi.yaml`

版本号在各自包目录里单独维护(基于 `uv version`):

```bash
just version-one lush-stdx
just bump-one lush-stdx patch
just set-version-one lush-stdx 0.1.1
```

## 一个小约定

示例与测试里尽量用 `example.com` / RFC TEST-NET 地址,不要提交真实凭据、内部域名/IP、真实用户数据.
