"""Tests for SyncMySQLManager and sync helper functions."""

from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
import yaml
from sqlalchemy import text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.pool import NullPool, StaticPool

from lush_sqlalchemyx.base.dal._sync import SyncSqlATableBase
from lush_sqlalchemyx.mgrs.mysql.sync_manager import (
    SyncMySQLManager,
    configured_session_temporarily,
    execute_sql,
    must_rollback_if_in_transaction,
)

TEST_CONFIG_PATH = Path(__file__).with_name("test_config.yaml")


def _make_broken_manager() -> SyncMySQLManager:
    """Create a manager whose health_check will always fail."""
    mgr = SyncMySQLManager.__new__(SyncMySQLManager)
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
    mgr.engine = engine
    # Bind the session to the engine, then invalidate the pool
    mgr.session_local = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    engine.dispose()
    # Replace session factory to always raise
    original = mgr.session_local

    class _BrokenSessionMaker:
        def __call__(self, **kw: Any) -> None:
            raise RuntimeError("connection refused")

    mgr.session_local = _BrokenSessionMaker()  # type: ignore[assignment]
    return mgr


def _load_sync_sqlite_uri() -> tuple[str, Path]:
    with TEST_CONFIG_PATH.open(encoding="utf-8") as f:
        config: dict[str, Any] = yaml.safe_load(f)
    mysql_cfg: dict[str, Any] = config.get("MYSQLDB", {})
    sqlite_rel = mysql_cfg.get("TEST_SQLITE_PATH", ".tmp/lush_sqlalchemyx_test.db")
    sqlite_path = (TEST_CONFIG_PATH.parent / sqlite_rel).resolve()
    sqlite_path = sqlite_path.with_name("sync_mgr_" + sqlite_path.name)
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{sqlite_path}", sqlite_path


class _ManagerTestTable(SyncSqlATableBase):
    __tablename__ = "sync_mgr_test"
    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(50), nullable=False)


class TestSyncMySQLManager:
    @pytest.fixture
    def manager(self):
        uri, path = _load_sync_sqlite_uri()
        mgr = SyncMySQLManager(uri, poolclass=NullPool, connect_args={"check_same_thread": False})
        SyncSqlATableBase.metadata.create_all(mgr.engine, checkfirst=True)
        yield mgr
        mgr.close()
        if path.exists():
            path.unlink()

    def test_manual_session(self, manager: SyncMySQLManager):
        with manager.got_manual_session() as session:
            session.add(_ManagerTestTable(name="manual"))
            session.flush()
            session.commit()

        with manager.got_manual_session() as session:
            result = session.execute(sa.select(_ManagerTestTable).where(_ManagerTestTable.name == "manual"))
            assert result.scalar_one_or_none() is not None

    def test_auto_commit_session(self, manager: SyncMySQLManager):
        with manager.got_soft_impl_auto_commit_session() as session:
            session.add(_ManagerTestTable(name="auto-commit"))
            session.flush()

        with manager.got_manual_session() as session:
            result = session.execute(sa.select(_ManagerTestTable).where(_ManagerTestTable.name == "auto-commit"))
            assert result.scalar_one_or_none() is not None

    def test_auto_commit_session_rollback_on_error(self, manager: SyncMySQLManager):
        with pytest.raises(RuntimeError):
            with manager.got_soft_impl_auto_commit_session() as session:
                session.add(_ManagerTestTable(name="rollback"))
                session.flush()
                raise RuntimeError("boom")

    def test_readonly_session(self, manager: SyncMySQLManager):
        with manager.got_readonly_session() as session:
            result = session.execute(text("SELECT 1"))
            assert result.scalar() == 1

    def test_readonly_session_rollback_on_error(self, manager: SyncMySQLManager):
        with pytest.raises(RuntimeError):
            with manager.got_readonly_session() as session:
                raise RuntimeError("boom")

    def test_manual_session_rollback_on_error(self, manager: SyncMySQLManager):
        with pytest.raises(RuntimeError):
            with manager.got_manual_session() as session:
                raise RuntimeError("boom")

    def test_health_check(self, manager: SyncMySQLManager):
        assert manager.health_check() is True

    def test_health_check_failure(self):
        mgr = _make_broken_manager()
        assert mgr.health_check() is False

    def test_execute_sql(self, manager: SyncMySQLManager):
        result = manager.execute_sql("SELECT 1")
        assert result.scalar() == 1

    def test_execute_sql_text_clause(self, manager: SyncMySQLManager):
        result = manager.execute_sql(text("SELECT 1"))
        assert result.scalar() == 1

    def test_from_engine(self, manager: SyncMySQLManager):
        mgr2 = SyncMySQLManager.from_engine(manager.engine)
        with mgr2.got_manual_session() as session:
            result = session.execute(text("SELECT 1"))
            assert result.scalar() == 1

    def test_poolclass_override(self):
        uri, path = _load_sync_sqlite_uri()
        uri = uri.replace("sync_mgr_", "sync_mgr_pool_")
        path = path.with_name(path.name.replace("sync_mgr_", "sync_mgr_pool_"))
        mgr = SyncMySQLManager(uri, poolclass=StaticPool, connect_args={"check_same_thread": False})
        assert mgr.health_check() is True
        mgr.close()
        if path.exists():
            path.unlink()

    def test_default_pool_no_poolclass(self):
        """Test the branch where poolclass is NOT in engine_kwargs (line 31->35)."""
        uri, path = _load_sync_sqlite_uri()
        uri = uri.replace("sync_mgr_", "sync_mgr_nopool_")
        path = path.with_name(path.name.replace("sync_mgr_", "sync_mgr_nopool_"))
        mgr = SyncMySQLManager(uri, connect_args={"check_same_thread": False})
        assert mgr.health_check() is True
        mgr.close()
        if path.exists():
            path.unlink()

    def test_execute_sql_with_params(self, manager: SyncMySQLManager):
        """Test execute_sql with non-None params (line 134->137)."""
        result = manager.execute_sql("SELECT :val", params={"val": 42})
        assert result.scalar() == 42


class TestExecuteSQL:
    def test_execute_sql_function(self):
        from sqlalchemy import create_engine

        engine = create_engine("sqlite:///:memory:")
        with engine.connect() as conn:
            result = execute_sql(conn, "SELECT 1")
            assert result.scalar() == 1

    def test_execute_sql_text_clause(self):
        from sqlalchemy import create_engine

        engine = create_engine("sqlite:///:memory:")
        with engine.connect() as conn:
            result = execute_sql(conn, text("SELECT 1"))
            assert result.scalar() == 1


class TestConfiguredSessionTemporarily:
    def test_autoflush_toggle(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        engine = create_engine("sqlite:///:memory:")
        Session_ = sessionmaker(bind=engine, autoflush=False)
        session = Session_()

        assert session.autoflush is False
        with configured_session_temporarily(session, autoflush=True):
            assert session.autoflush is True
        assert session.autoflush is False
        session.close()

    def test_autocommit_true(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        engine = create_engine("sqlite:///:memory:")
        SyncSqlATableBase.metadata.create_all(engine)
        Session_ = sessionmaker(bind=engine)
        session = Session_()

        with configured_session_temporarily(session, autocommit=True):
            pass
        session.close()

    def test_autoflush_unchanged(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        engine = create_engine("sqlite:///:memory:")
        Session_ = sessionmaker(bind=engine, autoflush=False)
        session = Session_()

        with configured_session_temporarily(session, autoflush=False):
            assert session.autoflush is False
        session.close()

    def test_rollback_on_error(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        engine = create_engine("sqlite:///:memory:")
        Session_ = sessionmaker(bind=engine)
        session = Session_()

        with pytest.raises(RuntimeError):
            with configured_session_temporarily(session, autoflush=True):
                raise RuntimeError("boom")
        session.close()


class TestMustRollback:
    def test_rollback_when_in_transaction(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        engine = create_engine("sqlite:///:memory:")
        SyncSqlATableBase.metadata.create_all(engine)
        Session_ = sessionmaker(bind=engine)
        session = Session_()
        session.execute(text("SELECT 1"))
        must_rollback_if_in_transaction(session)
        session.close()

    def test_no_rollback_when_no_transaction(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        engine = create_engine("sqlite:///:memory:")
        Session_ = sessionmaker(bind=engine)
        session = Session_()
        must_rollback_if_in_transaction(session)
        session.close()
