"""同步 MySQL 管理器映射 — ``mapper.py`` 的同步镜像."""

from __future__ import annotations

from contextlib import suppress
from enum import Enum
from typing import Any, Generic, TypeVar

from .sync_manager import SyncMySQLManager

SyncDBEnumT = TypeVar("SyncDBEnumT", bound=Enum)


class SyncMySQLManagersMapper(Generic[SyncDBEnumT]):
    def __init__(
        self,
        *,
        default_name: SyncDBEnumT,
        managers: dict[SyncDBEnumT, SyncMySQLManager] | None = None,
        binds: dict[SyncDBEnumT, str] | None = None,
        engine_options_default: dict[str, Any] | None = None,
        binds_engine_options: dict[SyncDBEnumT, dict[str, Any]] | None = None,
    ) -> None:
        resolved: dict[SyncDBEnumT, SyncMySQLManager] | None = managers
        if resolved is None and binds is not None:
            engine_options_default = engine_options_default or {}
            binds_engine_options = binds_engine_options or {}
            built: dict[SyncDBEnumT, SyncMySQLManager] = {}
            for key, uri in binds.items():
                per_opts: dict[str, Any] = dict(engine_options_default)
                per_opts.update(binds_engine_options.get(key) or {})
                built[key] = SyncMySQLManager(uri, **per_opts)
            resolved = built

        if not resolved:
            raise ValueError("SyncMySQLManagersMapper requires at least one manager (via managers or non-empty binds)")
        if default_name not in resolved:
            raise KeyError("Default enum not found in managers")
        self._managers: dict[SyncDBEnumT, SyncMySQLManager] = dict(resolved)
        self._default_name: SyncDBEnumT = default_name

    def get_manager(self, name: SyncDBEnumT | None = None) -> SyncMySQLManager:
        key = name if name is not None else self._default_name
        try:
            return self._managers[key]
        except KeyError as exc:  # pragma: no cover
            raise KeyError(f"Unknown datasource enum: {key!r}. Known: {list(self._managers.keys())}") from exc

    def health_check(self) -> dict[SyncDBEnumT, bool]:
        results: dict[SyncDBEnumT, bool] = {}
        for key, manager in self._managers.items():
            with suppress(Exception):
                results[key] = manager.health_check()
            if key not in results:
                results[key] = False
        return results

    def close(self) -> None:
        for manager in self._managers.values():
            with suppress(Exception):
                manager.close()
