# lush-collections — SSOT (Agent + Repo Conventions)

> This file is the single source of truth for how we evolve this monorepo.

## Upgrade Policy (No Compatibility by Default)

- When iterating/refactoring, **do not** keep legacy/compat code paths unless the user explicitly asks for compatibility.
- Prefer “upgrade everything to the new style” in one go, even if refactor cost is higher.

## Testing & Coverage Policy

### Coverage Targets

- **All packages except `lush-wecom`**: require **100% coverage** with **branch coverage**.
  - Tests must **fail** if coverage is not 100%.
  - Implementation: package `pyproject.toml` uses pytest-cov with `--cov-branch` and `--cov-fail-under=100`.
- **`lush-wecom` exception**:
  - **No 100% coverage requirement**.
  - Only maintain **partial, pure-function/unit tests**; do **not** require API/integration tests for it.

### External Dependencies in Tests

- If a package needs external services (e.g. Redis/MySQL), tests must be able to:
  - **Auto-up** the dependency via Docker at test start.
  - **Auto-down** (cleanup) at teardown.
  - Be **idempotent** (no leftover containers / data causing flakiness).
  - Use **randomized** namespaces/resources (e.g. random DB name / key prefix) and **auto-clean**.
  - **Prefer local Docker images** to avoid pulling (fast path), but still work when pulling is needed.

Current fixtures:
- Redis (used by `lush-redisx` tests):
  - Env: `LUSH_TEST_REDIS_IMAGE` (pinned in CI), optional `REDIS_HOST/REDIS_PORT/...` for external Redis.
- MySQL (used by `lush-sqlalchemyx` tests):
  - Env: `LUSH_TEST_MYSQL_IMAGE` (pinned in CI), optional `LUSH_TEST_MYSQL_CONTAINER`, `LUSH_TEST_MYSQL_ROOT_PASSWORD`.

### Mocking Policy

- Prefer **real behavior** (real code paths, real dependencies via Docker) over mocks.
- Avoid `unittest.mock` / `patch` outside of `lush-sentryx`.
- Allow minimal test doubles only when they are the most stable/low-cost way to cover:
  - deterministically unreachable branches,
  - optional dependency import branches,
  - rare error paths that would otherwise require brittle environment manipulation.
- **Explicit exception**: `lush-sentryx` may use monkeypatch / dummy modules to cover optional integrations and import-failure branches.

## CI / Publishing

- `.github/workflows/publish-pypi.yaml` runs `pytest` before publishing.
- CI must use **pinned Docker images** (no floating tags) for deterministic runs:
  - `LUSH_TEST_REDIS_IMAGE=redis:7.4-alpine`
  - `LUSH_TEST_MYSQL_IMAGE=mysql:8.0.40-debian`

## Release (Best Practices)

- Use **one commit + one tag per package**:
  - Commit message: `lush-<pkg>: bump version to <ver>`
  - Tag format: `lush-<pkg>-v<ver>` (this is what `publish-pypi.yaml` expects).
- Prefer pushing tags **one-by-one** via `git push origin <tag>` to reliably trigger `on.push.tags`.
  - Avoid relying on `git push --follow-tags` for publishing triggers.
- Use `just release-patch` for a safe, repeatable flow:
  - Patch-bumps each selected package, runs `just test-one <pkg>` (unless `RELEASE_SKIP_TESTS=1`),
  - creates the tag, pushes `main`, then pushes tags one-by-one and (by default) waits for GitHub Actions to complete.
