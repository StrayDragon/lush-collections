"""DynamicDAL 测试 — TableRef + DynamicSyncDAL + DynamicAsyncDAL.

覆盖:
- derive_columns_from_dto 各场景 (simple / alias / AliasChoices)
- derive_pk_from_dto 正常 + 无 id 字段
- TableRef 自动推导 + 用户覆盖
- DynamicSyncDAL CRUD 全流程 (SQLite)
- DynamicSyncDAL 软删除拦截 (SQLite)
- DynamicSyncDAL 只读保护 (SQLite)
- DynamicSyncDAL bulk_create (SQLite)
- DynamicAsyncDAL CRUD 全流程 (aiosqlite)
- DynamicAsyncDAL 软删除拦截 (aiosqlite)
- DynamicAsyncDAL 只读保护 (aiosqlite)
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from datetime import datetime

import pytest
import sqlalchemy as sa
from pydantic import AliasChoices, BaseModel, Field
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from lush_sqlalchemyx.base.dal._dynamic import (
    DynamicAsyncDAL,
    DynamicSyncDAL,
    TableRef,
    derive_columns_from_dto,
    derive_pk_from_dto,
)

# ================================================================
# Fixtures
# ================================================================


class SimpleDTO(BaseModel):
    id: int
    user_id: int
    action: str
    extra: str | None = None


class SimpleCU(BaseModel):
    user_id: int
    action: str
    extra: str | None = None


class AliasDTO(BaseModel):
    id: int
    user_id: int
    action: str
    extra: str | None = Field(None, alias="metadata_json")
    created_at: datetime = Field(alias="create_time")


class AliasCU(BaseModel, populate_by_name=True):
    user_id: int
    action: str
    extra: str | None = Field(None, alias="metadata_json")


class MultiAliasDTO(BaseModel):
    id: int
    name: str = Field(validation_alias=AliasChoices("db_name", "name", "full_name"))


class SoftDeleteDTO(BaseModel):
    id: int
    user_id: int
    action: str
    is_delete: int = 0


class NoDeleteFieldDTO(BaseModel):
    id: int
    user_id: int
    action: str


class NoIdDTO(BaseModel):
    user_id: int
    action: str


class ReadOnlyDTO(BaseModel):
    id: int
    user_id: int
    total: int


# ================================================================
# 推导函数测试
# ================================================================


class TestDeriveColumnsFromDto:
    """derive_columns_from_dto 测试."""

    def test_simple(self) -> None:
        cols = derive_columns_from_dto(SimpleDTO)
        assert cols == {
            "id": "id",
            "user_id": "user_id",
            "action": "action",
            "extra": "extra",
        }

    def test_alias(self) -> None:
        cols = derive_columns_from_dto(AliasDTO)
        assert cols["extra"] == "metadata_json"
        assert cols["created_at"] == "create_time"
        assert cols["id"] == "id"

    def test_alias_choices(self) -> None:
        cols = derive_columns_from_dto(MultiAliasDTO)
        assert cols["name"] == "db_name"


class TestDerivePkFromDto:
    """derive_pk_from_dto 测试."""

    def test_simple(self) -> None:
        assert derive_pk_from_dto(SimpleDTO) == "id"

    def test_alias(self) -> None:

        class AliasPkDTO(BaseModel):
            id: int = Field(alias="log_id")

        assert derive_pk_from_dto(AliasPkDTO) == "log_id"

    def test_no_id_field_raises(self) -> None:
        with pytest.raises(ValueError, match="没有 'id' 字段"):
            derive_pk_from_dto(NoIdDTO)


# ================================================================
# TableRef 测试
# ================================================================


class TestTableRef:
    """TableRef 推导与覆盖测试."""

    def test_of_full_auto(self) -> None:
        ref = TableRef.of("t", SimpleDTO)
        assert ref.resolved_pk_column == "id"
        assert ref.resolved_columns == {
            "id": "id",
            "user_id": "user_id",
            "action": "action",
            "extra": "extra",
        }

    def test_of_override_pk(self) -> None:
        ref = TableRef.of("t", SimpleDTO, pk_column="my_id")
        assert ref.resolved_pk_column == "my_id"
        # columns 仍然自动推导
        assert "user_id" in ref.resolved_columns

    def test_of_override_columns(self) -> None:
        ref = TableRef.of("t", SimpleDTO, columns={"user_id": "uid"})
        assert ref.resolved_columns == {"user_id": "uid"}
        # pk 仍然自动推导
        assert ref.resolved_pk_column == "id"

    def test_of_override_both(self) -> None:
        ref = TableRef.of("t", SimpleDTO, pk_column="log_id", columns={"user_id": "uid"})
        assert ref.resolved_pk_column == "log_id"
        assert ref.resolved_columns == {"user_id": "uid"}

    def test_of_alias_dto(self) -> None:
        ref = TableRef.of("t", AliasDTO)
        assert ref.resolved_pk_column == "id"
        assert ref.resolved_columns["extra"] == "metadata_json"
        assert ref.resolved_columns["created_at"] == "create_time"

    def test_with_soft_delete(self) -> None:
        ref = TableRef.with_soft_delete("t", SoftDeleteDTO)
        assert ref.config.soft_delete_column == "is_delete"
        assert ref.resolved_pk_column == "id"

    def test_with_soft_delete_override(self) -> None:
        ref = TableRef.with_soft_delete(
            "t",
            SoftDeleteDTO,
            pk_column="uid",
            columns={"user_id": "uid", "is_delete": "deleted"},
            soft_delete_column="deleted",
        )
        assert ref.resolved_pk_column == "uid"
        assert ref.config.soft_delete_column == "deleted"

    def test_readonly(self) -> None:
        ref = TableRef.readonly("t", SimpleDTO)
        assert ref.config.is_readonly is True

    def test_no_id_dto_raises_when_auto(self) -> None:
        ref = TableRef.of("t", NoIdDTO)
        with pytest.raises(ValueError, match="没有 'id' 字段"):
            _ = ref.resolved_pk_column

    def test_no_id_dto_ok_with_override(self) -> None:
        ref = TableRef.of("t", NoIdDTO, pk_column="user_id")
        assert ref.resolved_pk_column == "user_id"

    def test_map_to_row_data(self) -> None:
        ref = TableRef.of("t", SimpleDTO)
        cu = SimpleCU(user_id=1, action="click")
        row = ref.map_to_row_data(cu.model_dump(exclude_unset=True))
        assert row == {"user_id": 1, "action": "click"}

    def test_map_to_row_data_with_alias(self) -> None:
        ref = TableRef.of("t", AliasDTO)
        cu = AliasCU(user_id=1, action="click", extra="{}")
        row = ref.map_to_row_data(cu.model_dump(exclude_unset=True))
        assert row == {"user_id": 1, "action": "click", "metadata_json": "{}"}

    def test_map_from_row(self) -> None:
        ref = TableRef.of("t", AliasDTO)
        raw = {"id": 1, "user_id": 2, "action": "click", "metadata_json": "{}", "create_time": "2025-01-01T00:00:00"}
        py_data = ref.map_from_row(raw)
        # map_from_row 返回 model_validate 能识别的 key (alias/validation_alias)
        assert py_data["id"] == 1
        assert py_data["metadata_json"] == "{}"  # alias key
        assert py_data["create_time"] == "2025-01-01T00:00:00"  # alias key

    def test_guard_readonly_raises(self) -> None:
        ref = TableRef.readonly("t", SimpleDTO)
        with pytest.raises(TypeError, match="只读"):
            ref.guard_readonly("创建")

    def test_guard_readonly_pass_when_not_readonly(self) -> None:
        ref = TableRef.of("t", SimpleDTO)
        ref.guard_readonly("创建")  # 不抛


# ================================================================
# DynamicSyncDAL 测试 (SQLite)
# ================================================================


@pytest.fixture()
def sync_session() -> Generator[Session, None, None]:
    """SQLite 内存同步 Session."""
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            sa.text("""
            CREATE TABLE user_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                extra TEXT,
                is_delete INTEGER DEFAULT 0
            )
        """)
        )
        conn.execute(
            sa.text("""
            CREATE TABLE v_stats (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                total INTEGER NOT NULL
            )
        """)
        )
        conn.execute(sa.text("INSERT INTO v_stats (id, user_id, total) VALUES (1, 100, 42)"))
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as session:
        yield session


class TestDynamicSyncDALCrud:
    """DynamicSyncDAL CRUD 全流程."""

    def test_create_and_get(self, sync_session: Session) -> None:
        ref = TableRef.of("user_log", SimpleDTO)
        dal = DynamicSyncDAL(ref, SimpleDTO)

        dto = dal.create(SimpleCU(user_id=1, action="click", extra="home"), session=sync_session)
        assert dto.id == 1
        assert dto.user_id == 1
        assert dto.action == "click"

        got = dal.get_by_id(1, session=sync_session)
        assert got is not None
        assert got.id == 1

    def test_get_not_found(self, sync_session: Session) -> None:
        ref = TableRef.of("user_log", SimpleDTO)
        dal = DynamicSyncDAL(ref, SimpleDTO)
        assert dal.get_by_id(999, session=sync_session) is None

    def test_update(self, sync_session: Session) -> None:
        ref = TableRef.of("user_log", SimpleDTO)
        dal = DynamicSyncDAL(ref, SimpleDTO)
        dal.create(SimpleCU(user_id=1, action="click"), session=sync_session)

        count = dal.update_by_id(1, SimpleCU(user_id=1, action="view"), session=sync_session)
        assert count == 1

        got = dal.get_by_id(1, session=sync_session)
        assert got is not None
        assert got.action == "view"

    def test_update_not_found(self, sync_session: Session) -> None:
        ref = TableRef.of("user_log", SimpleDTO)
        dal = DynamicSyncDAL(ref, SimpleDTO)
        count = dal.update_by_id(999, SimpleCU(user_id=1, action="x"), session=sync_session)
        assert count == 0

    def test_hard_delete(self, sync_session: Session) -> None:
        ref = TableRef.of("user_log", SimpleDTO)
        dal = DynamicSyncDAL(ref, SimpleDTO)
        dal.create(SimpleCU(user_id=1, action="click"), session=sync_session)

        deleted = dal.delete_by_id(1, session=sync_session)
        assert deleted is True

        assert dal.get_by_id(1, session=sync_session) is None

    def test_hard_delete_not_found(self, sync_session: Session) -> None:
        ref = TableRef.of("user_log", SimpleDTO)
        dal = DynamicSyncDAL(ref, SimpleDTO)
        assert dal.delete_by_id(999, session=sync_session) is False

    def test_bulk_create(self, sync_session: Session) -> None:
        ref = TableRef.of("user_log", SimpleDTO)
        dal = DynamicSyncDAL(ref, SimpleDTO)

        n = dal.bulk_create(
            [
                SimpleCU(user_id=1, action="a"),
                SimpleCU(user_id=2, action="b"),
                SimpleCU(user_id=3, action="c"),
            ],
            session=sync_session,
        )
        assert n == 3

        dtos = dal.list_by(session=sync_session)
        assert len(dtos) == 3

    def test_bulk_create_empty(self, sync_session: Session) -> None:
        ref = TableRef.of("user_log", SimpleDTO)
        dal = DynamicSyncDAL(ref, SimpleDTO)
        assert dal.bulk_create([], session=sync_session) == 0

    def test_list_by(self, sync_session: Session) -> None:
        ref = TableRef.of("user_log", SimpleDTO)
        dal = DynamicSyncDAL(ref, SimpleDTO)
        dal.bulk_create(
            [
                SimpleCU(user_id=1, action="a"),
                SimpleCU(user_id=2, action="b"),
                SimpleCU(user_id=1, action="c"),
            ],
            session=sync_session,
        )

        dtos = dal.list_by([sa.column("user_id") == 1], session=sync_session)
        assert len(dtos) == 2

    def test_list_by_pagination(self, sync_session: Session) -> None:
        ref = TableRef.of("user_log", SimpleDTO)
        dal = DynamicSyncDAL(ref, SimpleDTO)
        dal.bulk_create([SimpleCU(user_id=i, action=f"a{i}") for i in range(10)], session=sync_session)

        dtos = dal.list_by(skip=0, limit=3, session=sync_session)
        assert len(dtos) == 3

        dtos2 = dal.list_by(skip=3, limit=3, session=sync_session)
        assert len(dtos2) == 3
        assert dtos2[0].id != dtos[0].id

    def test_count_by(self, sync_session: Session) -> None:
        ref = TableRef.of("user_log", SimpleDTO)
        dal = DynamicSyncDAL(ref, SimpleDTO)
        dal.bulk_create(
            [
                SimpleCU(user_id=1, action="a"),
                SimpleCU(user_id=2, action="b"),
                SimpleCU(user_id=1, action="c"),
            ],
            session=sync_session,
        )

        assert dal.count_by(session=sync_session) == 3
        assert dal.count_by([sa.column("user_id") == 1], session=sync_session) == 2


class TestDynamicSyncDALSoftDelete:
    """DynamicSyncDAL 软删除拦截."""

    def _make_dal(self) -> tuple[TableRef, DynamicSyncDAL[SoftDeleteDTO]]:
        ref = TableRef.with_soft_delete(
            "user_log",
            NoDeleteFieldDTO,
            soft_delete_column="is_delete",
        )
        dal = DynamicSyncDAL(ref, NoDeleteFieldDTO)
        return ref, dal

    def test_create_returns_dto(self, sync_session: Session) -> None:
        _, dal = self._make_dal()
        dto = dal.create(SimpleCU(user_id=1, action="click"), session=sync_session)
        assert dto.id == 1

    def test_soft_delete(self, sync_session: Session) -> None:
        _, dal = self._make_dal()
        dal.create(SimpleCU(user_id=1, action="click"), session=sync_session)

        deleted = dal.delete_by_id(1, session=sync_session)
        assert deleted is True

        # 软删除后查不到
        assert dal.get_by_id(1, session=sync_session) is None

    def test_soft_delete_excludes_from_list(self, sync_session: Session) -> None:
        _, dal = self._make_dal()
        dal.bulk_create(
            [
                SimpleCU(user_id=1, action="a"),
                SimpleCU(user_id=2, action="b"),
                SimpleCU(user_id=3, action="c"),
            ],
            session=sync_session,
        )

        dal.delete_by_id(1, session=sync_session)

        dtos = dal.list_by(session=sync_session)
        assert len(dtos) == 2

        dtos_all = dal.list_by(include_deleted=True, session=sync_session)
        assert len(dtos_all) == 3

    def test_soft_delete_excludes_from_count(self, sync_session: Session) -> None:
        _, dal = self._make_dal()
        dal.bulk_create(
            [
                SimpleCU(user_id=1, action="a"),
                SimpleCU(user_id=2, action="b"),
            ],
            session=sync_session,
        )

        assert dal.count_by(session=sync_session) == 2

        dal.delete_by_id(1, session=sync_session)
        assert dal.count_by(session=sync_session) == 1
        assert dal.count_by(include_deleted=True, session=sync_session) == 2

    def test_restore(self, sync_session: Session) -> None:
        _, dal = self._make_dal()
        dal.create(SimpleCU(user_id=1, action="click"), session=sync_session)

        dal.delete_by_id(1, session=sync_session)
        assert dal.get_by_id(1, session=sync_session) is None

        restored = dal.restore_by_id(1, session=sync_session)
        assert restored is True

        dto = dal.get_by_id(1, session=sync_session)
        assert dto is not None
        assert dto.id == 1

    def test_restore_not_found(self, sync_session: Session) -> None:
        _, dal = self._make_dal()
        assert dal.restore_by_id(999, session=sync_session) is False

    def test_restore_without_soft_delete_config_raises(self, sync_session: Session) -> None:
        ref = TableRef.of("user_log", SimpleDTO)
        dal = DynamicSyncDAL(ref, SimpleDTO)
        with pytest.raises(TypeError, match="未配置软删除"):
            dal.restore_by_id(1, session=sync_session)


class TestDynamicSyncDALReadonly:
    """DynamicSyncDAL 只读保护."""

    def _make_dal(self) -> DynamicSyncDAL[ReadOnlyDTO]:
        ref = TableRef.readonly("v_stats", ReadOnlyDTO)
        return DynamicSyncDAL(ref, ReadOnlyDTO)

    def test_read_ok(self, sync_session: Session) -> None:
        dal = self._make_dal()
        dto = dal.get_by_id(1, session=sync_session)
        assert dto is not None
        assert dto.total == 42

    def test_list_ok(self, sync_session: Session) -> None:
        dal = self._make_dal()
        dtos = dal.list_by(session=sync_session)
        assert len(dtos) == 1

    def test_count_ok(self, sync_session: Session) -> None:
        dal = self._make_dal()
        assert dal.count_by(session=sync_session) == 1

    def test_create_raises(self, sync_session: Session) -> None:
        dal = self._make_dal()
        with pytest.raises(TypeError, match="只读"):
            dal.create(SimpleCU(user_id=999, action="hack"), session=sync_session)

    def test_update_raises(self, sync_session: Session) -> None:
        dal = self._make_dal()
        with pytest.raises(TypeError, match="只读"):
            dal.update_by_id(1, SimpleCU(user_id=1, action="hack"), session=sync_session)

    def test_delete_raises(self, sync_session: Session) -> None:
        dal = self._make_dal()
        with pytest.raises(TypeError, match="只读"):
            dal.delete_by_id(1, session=sync_session)

    def test_bulk_create_raises(self, sync_session: Session) -> None:
        dal = self._make_dal()
        with pytest.raises(TypeError, match="只读"):
            dal.bulk_create([SimpleCU(user_id=1, action="hack")], session=sync_session)


# ================================================================
# DynamicAsyncDAL 测试 (aiosqlite)
# ================================================================


@pytest.fixture()
async def async_session() -> AsyncGenerator[AsyncSession, None]:
    """aiosqlite 内存异步 Session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.execute(
            sa.text("""
            CREATE TABLE user_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                extra TEXT,
                is_delete INTEGER DEFAULT 0
            )
        """)
        )
        await conn.execute(
            sa.text("""
            CREATE TABLE v_stats (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                total INTEGER NOT NULL
            )
        """)
        )
        await conn.execute(sa.text("INSERT INTO v_stats (id, user_id, total) VALUES (1, 100, 42)"))
    SessionLocal = async_sessionmaker(bind=engine)
    async with SessionLocal() as session:
        yield session


class TestDynamicAsyncDALCrud:
    """DynamicAsyncDAL CRUD 全流程."""

    async def test_create_and_get(self, async_session: AsyncSession) -> None:
        ref = TableRef.of("user_log", SimpleDTO)
        dal = DynamicAsyncDAL(ref, SimpleDTO)

        dto = await dal.create(SimpleCU(user_id=1, action="click", extra="home"), session=async_session)
        assert dto.id == 1
        assert dto.user_id == 1

        got = await dal.get_by_id(1, session=async_session)
        assert got is not None
        assert got.id == 1

    async def test_get_not_found(self, async_session: AsyncSession) -> None:
        ref = TableRef.of("user_log", SimpleDTO)
        dal = DynamicAsyncDAL(ref, SimpleDTO)
        assert await dal.get_by_id(999, session=async_session) is None

    async def test_update(self, async_session: AsyncSession) -> None:
        ref = TableRef.of("user_log", SimpleDTO)
        dal = DynamicAsyncDAL(ref, SimpleDTO)
        await dal.create(SimpleCU(user_id=1, action="click"), session=async_session)

        count = await dal.update_by_id(1, SimpleCU(user_id=1, action="view"), session=async_session)
        assert count == 1

    async def test_hard_delete(self, async_session: AsyncSession) -> None:
        ref = TableRef.of("user_log", SimpleDTO)
        dal = DynamicAsyncDAL(ref, SimpleDTO)
        await dal.create(SimpleCU(user_id=1, action="click"), session=async_session)

        deleted = await dal.delete_by_id(1, session=async_session)
        assert deleted is True
        assert await dal.get_by_id(1, session=async_session) is None

    async def test_bulk_create(self, async_session: AsyncSession) -> None:
        ref = TableRef.of("user_log", SimpleDTO)
        dal = DynamicAsyncDAL(ref, SimpleDTO)

        n = await dal.bulk_create(
            [
                SimpleCU(user_id=1, action="a"),
                SimpleCU(user_id=2, action="b"),
            ],
            session=async_session,
        )
        assert n == 2

    async def test_list_by(self, async_session: AsyncSession) -> None:
        ref = TableRef.of("user_log", SimpleDTO)
        dal = DynamicAsyncDAL(ref, SimpleDTO)
        await dal.bulk_create(
            [
                SimpleCU(user_id=1, action="a"),
                SimpleCU(user_id=2, action="b"),
                SimpleCU(user_id=1, action="c"),
            ],
            session=async_session,
        )

        dtos = await dal.list_by([sa.column("user_id") == 1], session=async_session)
        assert len(dtos) == 2

    async def test_count_by(self, async_session: AsyncSession) -> None:
        ref = TableRef.of("user_log", SimpleDTO)
        dal = DynamicAsyncDAL(ref, SimpleDTO)
        await dal.bulk_create(
            [
                SimpleCU(user_id=1, action="a"),
                SimpleCU(user_id=2, action="b"),
            ],
            session=async_session,
        )

        assert await dal.count_by(session=async_session) == 2
        assert await dal.count_by([sa.column("user_id") == 1], session=async_session) == 1


class TestDynamicAsyncDALSoftDelete:
    """DynamicAsyncDAL 软删除拦截."""

    async def test_soft_delete_and_restore(self, async_session: AsyncSession) -> None:
        ref = TableRef.with_soft_delete("user_log", NoDeleteFieldDTO, soft_delete_column="is_delete")
        dal = DynamicAsyncDAL(ref, NoDeleteFieldDTO)

        await dal.create(SimpleCU(user_id=1, action="click"), session=async_session)

        await dal.delete_by_id(1, session=async_session)
        assert await dal.get_by_id(1, session=async_session) is None

        await dal.restore_by_id(1, session=async_session)
        dto = await dal.get_by_id(1, session=async_session)
        assert dto is not None

    async def test_soft_delete_excludes_from_list(self, async_session: AsyncSession) -> None:
        ref = TableRef.with_soft_delete("user_log", NoDeleteFieldDTO, soft_delete_column="is_delete")
        dal = DynamicAsyncDAL(ref, NoDeleteFieldDTO)

        await dal.bulk_create(
            [
                SimpleCU(user_id=1, action="a"),
                SimpleCU(user_id=2, action="b"),
            ],
            session=async_session,
        )
        await dal.delete_by_id(1, session=async_session)

        assert len(await dal.list_by(session=async_session)) == 1
        assert len(await dal.list_by(include_deleted=True, session=async_session)) == 2

    async def test_soft_delete_excludes_from_count(self, async_session: AsyncSession) -> None:
        ref = TableRef.with_soft_delete("user_log", NoDeleteFieldDTO, soft_delete_column="is_delete")
        dal = DynamicAsyncDAL(ref, NoDeleteFieldDTO)

        await dal.bulk_create(
            [
                SimpleCU(user_id=1, action="a"),
                SimpleCU(user_id=2, action="b"),
            ],
            session=async_session,
        )
        await dal.delete_by_id(1, session=async_session)

        assert await dal.count_by(session=async_session) == 1
        assert await dal.count_by(include_deleted=True, session=async_session) == 2

    async def test_restore_without_config_raises(self, async_session: AsyncSession) -> None:
        ref = TableRef.of("user_log", SimpleDTO)
        dal = DynamicAsyncDAL(ref, SimpleDTO)
        with pytest.raises(TypeError, match="未配置软删除"):
            await dal.restore_by_id(1, session=async_session)


class TestDynamicAsyncDALReadonly:
    """DynamicAsyncDAL 只读保护."""

    async def test_read_ok(self, async_session: AsyncSession) -> None:
        ref = TableRef.readonly("v_stats", ReadOnlyDTO)
        dal = DynamicAsyncDAL(ref, ReadOnlyDTO)
        dto = await dal.get_by_id(1, session=async_session)
        assert dto is not None
        assert dto.total == 42

    async def test_create_raises(self, async_session: AsyncSession) -> None:
        ref = TableRef.readonly("v_stats", ReadOnlyDTO)
        dal = DynamicAsyncDAL(ref, ReadOnlyDTO)
        with pytest.raises(TypeError, match="只读"):
            await dal.create(SimpleCU(user_id=999, action="hack"), session=async_session)

    async def test_delete_raises(self, async_session: AsyncSession) -> None:
        ref = TableRef.readonly("v_stats", ReadOnlyDTO)
        dal = DynamicAsyncDAL(ref, ReadOnlyDTO)
        with pytest.raises(TypeError, match="只读"):
            await dal.delete_by_id(1, session=async_session)

    async def test_bulk_create_raises(self, async_session: AsyncSession) -> None:
        ref = TableRef.readonly("v_stats", ReadOnlyDTO)
        dal = DynamicAsyncDAL(ref, ReadOnlyDTO)
        with pytest.raises(TypeError, match="只读"):
            await dal.bulk_create([SimpleCU(user_id=1, action="hack")], session=async_session)


# ================================================================
# 覆盖盲区补充测试
# ================================================================


class TestCoverageEdgeCases:
    """覆盖 review 发现的盲区."""

    def test_resolve_alias_returns_none_for_plain_field(self) -> None:
        """无 alias 的字段, _resolve_alias 返回 None, derive 回退到 field_name."""
        from pydantic import BaseModel

        class PlainDTO(BaseModel):
            name: str  # 无 alias
            age: int

        columns = derive_columns_from_dto(PlainDTO)
        assert columns == {"name": "name", "age": "age"}

    def test_pk_field_name_fallback_when_pk_not_in_columns(self) -> None:
        """手动指定 pk_column 且不在 columns 映射中, 回退到 db column 名."""
        ref = TableRef(
            table_name="t",
            pk_column="custom_pk",
            columns={"name": "name_col"},
        )
        # custom_pk 不在 columns values 中
        assert ref.pk_field_name == "custom_pk"

    def test_bulk_create_empty_iterable(self, sync_session: Session) -> None:
        """空迭代器批量创建返回 0."""
        dal = DynamicSyncDAL(TableRef.of("dyn_items", SimpleDTO), SimpleDTO)
        result = dal.bulk_create([], session=sync_session)
        assert result == 0

    def test_bulk_create_empty_generator(self, sync_session: Session) -> None:
        """空生成器批量创建返回 0."""

        def empty_gen():
            yield from []

        dal = DynamicSyncDAL(TableRef.of("dyn_items", SimpleDTO), SimpleDTO)
        result = dal.bulk_create(empty_gen(), session=sync_session)
        assert result == 0


# ================================================================
# 导入测试
# ================================================================


class TestImports:
    """验证顶层导出."""

    def test_import_from_dal(self) -> None:
        from lush_sqlalchemyx.base.dal import (
            DynamicAsyncDAL,
            DynamicSyncDAL,
            TableRef,
        )

        assert TableRef is not None
        assert DynamicSyncDAL is not None
        assert DynamicAsyncDAL is not None

    def test_import_from_top_level(self) -> None:
        from lush_sqlalchemyx import (
            TableRef,
        )

        assert TableRef is not None


class TestSessionResolution:
    """验证 session 构造注入 + keyword arg 解析."""

    def test_sync_no_session_raises(self) -> None:
        """未注入 session 且调用时未传入, 抛出 RuntimeError."""
        dal = DynamicSyncDAL(TableRef.of("user_log", SimpleDTO), SimpleDTO)
        with pytest.raises(RuntimeError, match="未提供 session"):
            dal.get_by_id(1)

    def test_sync_injected_session(self, sync_session: Session) -> None:
        """构造注入 session, 调用时无需传入."""
        dal = DynamicSyncDAL(TableRef.of("user_log", SimpleDTO), SimpleDTO, session=sync_session)
        dal.create(SimpleCU(user_id=1, action="test"))
        got = dal.get_by_id(1)
        assert got is not None
        assert got.action == "test"

    def test_sync_explicit_overrides_injected(self, sync_session: Session) -> None:
        """显式传入 session 覆盖构造注入."""
        dal = DynamicSyncDAL(TableRef.of("user_log", SimpleDTO), SimpleDTO, session=sync_session)
        dal.create(SimpleCU(user_id=1, action="test"), session=sync_session)
        assert dal.get_by_id(1, session=sync_session) is not None

    def test_sync_of_with_session(self, sync_session: Session) -> None:
        """工厂方法 of 也支持 session 参数."""
        dal = DynamicSyncDAL.of(TableRef.of("user_log", SimpleDTO), SimpleDTO, session=sync_session)
        dal.create(SimpleCU(user_id=1, action="test"))
        assert dal.get_by_id(1) is not None

    @pytest.mark.asyncio
    async def test_async_no_session_raises(self) -> None:
        """异步 DAL 未注入 session 时抛出 RuntimeError."""
        dal = DynamicAsyncDAL(TableRef.of("user_log", SimpleDTO), SimpleDTO)
        with pytest.raises(RuntimeError, match="未提供 session"):
            await dal.get_by_id(1)

    @pytest.mark.asyncio
    async def test_async_of_with_session(self, async_session: AsyncSession) -> None:
        """异步工厂方法 of 支持 session 参数."""
        dal = DynamicAsyncDAL.of(TableRef.of("user_log", SimpleDTO), SimpleDTO, session=async_session)
        await dal.create(SimpleCU(user_id=1, action="test"))
        assert await dal.get_by_id(1) is not None
