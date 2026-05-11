"""Tests for Flask-SQLAlchemy integration."""

import pytest
import sqlalchemy as sa
from flask import Flask, g
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import Mapped, Session, mapped_column

from lush_sqlalchemyx.integrations.flask import LushFlaskSQLAlchemy, MySQLManagerMapperFlaskDepends
from lush_sqlalchemyx.mgrs.mysql.sync_manager import SyncMySQLManager
from lush_sqlalchemyx.mgrs.mysql.sync_mapper import SyncMySQLManagersMapper

from enum import Enum


class _TestDB(Enum):
    DEFAULT = "default"


@pytest.fixture
def flask_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["TESTING"] = True
    return app


@pytest.fixture
def flask_db(flask_app):
    db = SQLAlchemy()
    db.init_app(flask_app)
    with flask_app.app_context():
        yield db


class TestLushFlaskSQLAlchemy:
    def test_init_with_db(self, flask_db, flask_app):
        with flask_app.app_context():
            lush = LushFlaskSQLAlchemy(flask_db)
            assert lush.get_manager() is not None
            assert isinstance(lush.manager, SyncMySQLManager)

    def test_delayed_init(self, flask_db, flask_app):
        with flask_app.app_context():
            lush = LushFlaskSQLAlchemy()
            with pytest.raises(RuntimeError, match="not initialized"):
                lush.manager

            lush.init_db(flask_db)
            assert lush.get_manager() is not None

    def test_health_check(self, flask_db, flask_app):
        with flask_app.app_context():
            lush = LushFlaskSQLAlchemy(flask_db)
            assert lush.get_manager().health_check() is True


class TestMySQLManagerMapperFlaskDepends:
    def test_get_mapper(self, flask_app, flask_db):
        with flask_app.app_context():
            mgr = SyncMySQLManager.from_engine(flask_db.engine)
            mapper = SyncMySQLManagersMapper(
                default_name=_TestDB.DEFAULT,
                managers={_TestDB.DEFAULT: mgr},
            )
            g.mysql_mgrs_mapper = mapper

            result = MySQLManagerMapperFlaskDepends.get_mapper()
            assert result is mapper

    def test_get_mapper_missing(self, flask_app):
        with flask_app.app_context():
            with pytest.raises(RuntimeError, match="not found"):
                MySQLManagerMapperFlaskDepends.get_mapper()

    def test_get_manager_by_bind(self, flask_app, flask_db):
        with flask_app.app_context():
            mgr = SyncMySQLManager.from_engine(flask_db.engine)
            mapper = SyncMySQLManagersMapper(
                default_name=_TestDB.DEFAULT,
                managers={_TestDB.DEFAULT: mgr},
            )
            g.mysql_mgrs_mapper = mapper

            result = MySQLManagerMapperFlaskDepends.get_manager_by_bind(_TestDB.DEFAULT)
            assert result is mgr

    def test_get_manual_session(self, flask_app, flask_db):
        with flask_app.app_context():
            mgr = SyncMySQLManager.from_engine(flask_db.engine)
            mapper = SyncMySQLManagersMapper(
                default_name=_TestDB.DEFAULT,
                managers={_TestDB.DEFAULT: mgr},
            )
            g.mysql_mgrs_mapper = mapper

            with MySQLManagerMapperFlaskDepends.get_manual_session(_TestDB.DEFAULT) as session:
                assert isinstance(session, Session)
                result = session.execute(sa.text("SELECT 1"))
                assert result.scalar() == 1

    def test_get_tx_session(self, flask_app, flask_db):
        with flask_app.app_context():
            mgr = SyncMySQLManager.from_engine(flask_db.engine)
            mapper = SyncMySQLManagersMapper(
                default_name=_TestDB.DEFAULT,
                managers={_TestDB.DEFAULT: mgr},
            )
            g.mysql_mgrs_mapper = mapper

            with MySQLManagerMapperFlaskDepends.get_tx_session(_TestDB.DEFAULT) as session:
                assert isinstance(session, Session)

    def test_get_ro_session(self, flask_app, flask_db):
        with flask_app.app_context():
            mgr = SyncMySQLManager.from_engine(flask_db.engine)
            mapper = SyncMySQLManagersMapper(
                default_name=_TestDB.DEFAULT,
                managers={_TestDB.DEFAULT: mgr},
            )
            g.mysql_mgrs_mapper = mapper

            with MySQLManagerMapperFlaskDepends.get_ro_session(_TestDB.DEFAULT) as session:
                assert isinstance(session, Session)
