"""Flask-SQLAlchemy 集成测试."""

import pytest
import sqlalchemy as sa
from flask import Flask, g
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import Mapped, Session, mapped_column
from typing import ClassVar

from lush_sqlalchemyx.integrations.flask import FlaskSessionDALAdapter, LushFlaskSQLAlchemy, MySQLManagerMapperFlaskDepends
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


# ---------------------------------------------------------------------------
# 路径 2: FlaskSessionDALAdapter 测试
# ---------------------------------------------------------------------------

from pydantic import ConfigDict
from lush_sqlalchemyx.base.dal._common import BaseCU, BaseDTO
from lush_sqlalchemyx.base.dal._sync import SyncBaseDAL, SyncSqlATableBase


_flask_dal_db = SQLAlchemy(model_class=SyncSqlATableBase)


class _FlaskItem(_flask_dal_db.Model):
    __tablename__ = "flask_adapter_item"
    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(50))


class _FlaskItemCU(BaseCU["_FlaskItem"]):
    _Table: ClassVar[type] = _FlaskItem
    name: str


class _FlaskItemDTO(BaseDTO[_FlaskItemCU]):
    _CU: ClassVar[type[_FlaskItemCU]] = _FlaskItemCU
    id: int
    name: str
    model_config = ConfigDict(from_attributes=True)


class _FlaskItemDAL(SyncBaseDAL["_FlaskItem", _FlaskItemDTO, _FlaskItemCU]):
    _Table = _FlaskItem
    _DTO = _FlaskItemDTO


class _FlaskItemAdapterDAL(FlaskSessionDALAdapter["_FlaskItem", _FlaskItemDTO, _FlaskItemCU]):
    _dal_class = _FlaskItemDAL


@pytest.fixture
def flask_dal_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["TESTING"] = True
    _flask_dal_db.init_app(app)

    with app.app_context():
        _flask_dal_db.create_all()
        FlaskSessionDALAdapter.bind_db(_flask_dal_db)
        yield app, _flask_dal_db, _FlaskItemAdapterDAL, _FlaskItemCU


class TestFlaskSessionDALAdapter:
    def test_not_bound_raises(self):
        FlaskSessionDALAdapter._db = None

        class _Dummy(FlaskSessionDALAdapter):
            _dal_class = None

        adapter = _Dummy()
        with pytest.raises(RuntimeError, match="not bound"):
            _ = adapter.session

    def test_create_and_get_by_id(self, flask_dal_app):
        app, db, DAL, CU = flask_dal_app
        with app.app_context():
            dal = DAL()
            entity = dal.create(CU(name="hello"))
            db.session.commit()
            found = dal.get_by_id(entity.id)
            assert found is not None
            assert found.name == "hello"

    def test_get_by_id_nonexistent(self, flask_dal_app):
        app, db, DAL, CU = flask_dal_app
        with app.app_context():
            dal = DAL()
            assert dal.get_by_id(999999) is None

    def test_get_all(self, flask_dal_app):
        app, db, DAL, CU = flask_dal_app
        with app.app_context():
            dal = DAL()
            dal.create(CU(name="a"))
            dal.create(CU(name="b"))
            db.session.commit()
            all_items = dal.get_all()
            assert len(all_items) >= 2

    def test_count(self, flask_dal_app):
        app, db, DAL, CU = flask_dal_app
        with app.app_context():
            dal = DAL()
            before = dal.count()
            dal.create(CU(name="c"))
            db.session.commit()
            assert dal.count() == before + 1

    def test_exists(self, flask_dal_app):
        app, db, DAL, CU = flask_dal_app
        with app.app_context():
            dal = DAL()
            entity = dal.create(CU(name="x"))
            db.session.commit()
            assert dal.exists(entity.id) is True
            assert dal.exists(999999) is False

    def test_ret_dto_after_get_by_id(self, flask_dal_app):
        app, db, DAL, CU = flask_dal_app
        with app.app_context():
            dal = DAL()
            entity = dal.create(CU(name="dto"))
            db.session.commit()
            dto = dal.ret_dto_after_get_by_id(entity.id)
            assert dto is not None
            assert dto.name == "dto"
            assert dal.ret_dto_after_get_by_id(999999) is None

    def test_batch_get(self, flask_dal_app):
        app, db, DAL, CU = flask_dal_app
        with app.app_context():
            dal = DAL()
            e1 = dal.create(CU(name="b1"))
            e2 = dal.create(CU(name="b2"))
            db.session.commit()

            entities = dal.batch_get_id__entity([e1.id, e2.id, 999999])
            assert e1.id in entities
            assert 999999 not in entities

            dtos = dal.batch_get_id__dto([e1.id])
            assert e1.id in dtos

    def test_ret_dto_after_create(self, flask_dal_app):
        app, db, DAL, CU = flask_dal_app
        with app.app_context():
            dal = DAL()
            dto = dal.ret_dto_after_create(CU(name="new"))
            db.session.commit()
            assert dto.name == "new"

    def test_update_only_set_by_id(self, flask_dal_app):
        app, db, DAL, CU = flask_dal_app
        with app.app_context():
            dal = DAL()
            entity = dal.create(CU(name="old"))
            db.session.commit()
            updated = dal.update_only_set_by_id(entity.id, CU(name="new"))
            db.session.commit()
            assert updated is not None
            assert updated.name == "new"
            assert dal.update_only_set_by_id(999999, CU(name="x")) is None

    def test_delete_by_id(self, flask_dal_app):
        app, db, DAL, CU = flask_dal_app
        with app.app_context():
            dal = DAL()
            entity = dal.create(CU(name="del"))
            db.session.commit()
            assert dal.delete_by_id(entity.id) is True
            db.session.commit()
            assert dal.delete_by_id(999999) is False

    def test_iter_record_dtos(self, flask_dal_app):
        app, db, DAL, CU = flask_dal_app
        with app.app_context():
            dal = DAL()
            dal.create(CU(name="iter1"))
            dal.create(CU(name="iter2"))
            db.session.commit()
            records = list(dal.iter_record_dtos(batch_size=10))
            assert len(records) >= 2
