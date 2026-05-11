"""Tests for SyncMySQLManagersMapper."""

from enum import Enum

import pytest
from sqlalchemy.pool import StaticPool

from lush_sqlalchemyx.mgrs.mysql.sync_manager import SyncMySQLManager
from lush_sqlalchemyx.mgrs.mysql.sync_mapper import SyncMySQLManagersMapper


class _DB(Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"


def _make_manager() -> SyncMySQLManager:
    return SyncMySQLManager("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})


class TestSyncMapper:
    def test_init_with_managers(self):
        mgr = _make_manager()
        mapper = SyncMySQLManagersMapper(default_name=_DB.PRIMARY, managers={_DB.PRIMARY: mgr})
        assert mapper.get_manager() is mgr
        assert mapper.get_manager(_DB.PRIMARY) is mgr
        mgr.close()

    def test_init_with_binds(self):
        mapper = SyncMySQLManagersMapper(
            default_name=_DB.PRIMARY,
            binds={
                _DB.PRIMARY: "sqlite:///:memory:",
                _DB.SECONDARY: "sqlite:///:memory:",
            },
            engine_options_default={"poolclass": StaticPool, "connect_args": {"check_same_thread": False}},
        )
        assert mapper.get_manager(_DB.PRIMARY) is not None
        assert mapper.get_manager(_DB.SECONDARY) is not None
        mapper.close()

    def test_init_with_binds_per_opts(self):
        mapper = SyncMySQLManagersMapper(
            default_name=_DB.PRIMARY,
            binds={_DB.PRIMARY: "sqlite:///:memory:"},
            engine_options_default={"poolclass": StaticPool},
            binds_engine_options={_DB.PRIMARY: {"connect_args": {"check_same_thread": False}}},
        )
        assert mapper.get_manager() is not None
        mapper.close()

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="requires at least one"):
            SyncMySQLManagersMapper(default_name=_DB.PRIMARY, managers={})

    def test_default_not_in_managers(self):
        mgr = _make_manager()
        with pytest.raises(KeyError, match="Default enum not found"):
            SyncMySQLManagersMapper(default_name=_DB.SECONDARY, managers={_DB.PRIMARY: mgr})
        mgr.close()

    def test_health_check(self):
        mapper = SyncMySQLManagersMapper(
            default_name=_DB.PRIMARY,
            binds={_DB.PRIMARY: "sqlite:///:memory:"},
            engine_options_default={"poolclass": StaticPool, "connect_args": {"check_same_thread": False}},
        )
        results = mapper.health_check()
        assert results[_DB.PRIMARY] is True
        mapper.close()

    def test_health_check_failure(self):
        from unittest.mock import MagicMock

        mgr = _make_manager()
        mgr.health_check = MagicMock(side_effect=RuntimeError("connection refused"))
        mapper = SyncMySQLManagersMapper(default_name=_DB.PRIMARY, managers={_DB.PRIMARY: mgr})
        results = mapper.health_check()
        assert results[_DB.PRIMARY] is False
        mgr.close()

    def test_close_idempotent(self):
        mapper = SyncMySQLManagersMapper(
            default_name=_DB.PRIMARY,
            binds={_DB.PRIMARY: "sqlite:///:memory:"},
            engine_options_default={"poolclass": StaticPool, "connect_args": {"check_same_thread": False}},
        )
        mapper.close()
        mapper.close()

    def test_no_managers_no_binds(self):
        with pytest.raises(ValueError):
            SyncMySQLManagersMapper(default_name=_DB.PRIMARY)
