from __future__ import annotations

from contextlib import suppress
from enum import Enum
from typing import Any, Generic, TypeVar

from .manager import AsyncMySQLManager

DBEnumT = TypeVar("DBEnumT", bound=Enum)


class AsyncMySQLManagersMapper(Generic[DBEnumT]):
    def __init__(
        self,
        *,
        default_name: DBEnumT,
        managers: dict[DBEnumT, AsyncMySQLManager] | None = None,
        binds: dict[DBEnumT, str] | None = None,
        engine_options_default: dict[str, Any] | None = None,
        binds_engine_options: dict[DBEnumT, dict[str, Any]] | None = None,
    ) -> None:
        resolved: dict[DBEnumT, AsyncMySQLManager] | None = managers
        if resolved is None and binds is not None:
            engine_options_default = engine_options_default or {}
            binds_engine_options = binds_engine_options or {}
            built: dict[DBEnumT, AsyncMySQLManager] = {}
            for key, uri in binds.items():
                per_opts: dict[str, Any] = dict(engine_options_default)
                per_opts.update(binds_engine_options.get(key) or {})
                built[key] = AsyncMySQLManager(uri, **per_opts)
            resolved = built

        if not resolved:
            raise ValueError("AsyncMySQLManagersMapper requires at least one manager (via managers or non-empty binds)")
        if default_name not in resolved:
            raise KeyError("Default enum not found in managers")
        self._managers: dict[DBEnumT, AsyncMySQLManager] = dict(resolved)
        self._default_name: DBEnumT = default_name

    def get_manager(self, name: DBEnumT | None = None) -> AsyncMySQLManager:
        key = name if name is not None else self._default_name
        try:
            return self._managers[key]
        except KeyError as exc:  # pragma: no cover
            raise KeyError(f"Unknown datasource enum: {key!r}. Known: {list(self._managers.keys())}") from exc

    async def health_check(self) -> dict[DBEnumT, bool]:
        results: dict[DBEnumT, bool] = {}
        for key, manager in self._managers.items():
            results[key] = await manager.health_check()
        return results

    async def close(self) -> None:
        for manager in self._managers.values():
            with suppress(Exception):
                await manager.close()
