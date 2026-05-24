"""SQLAlchemy 具体 Repository 实现.

提供高层声明式 CRUD 接口, 内部委托给 DAL V2.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from contextlib import contextmanager
from typing import Any, ClassVar, Generic, TypeVar

import sqlalchemy as sa
from lush_dal_protocol.params.pagination import CursorPagination, CursorResult, OffsetPagination, PageResult
from lush_dal_protocol.repository import AbstractAsyncRepository, AbstractSyncRepository

from ._common import CUModelT, DTOModelT
from ._pagination import build_cursor_stmt, build_offset_stmt, make_cursor_result, make_page_result

TableT = TypeVar("TableT")


class SyncSQLAlchemyRepository(
    AbstractSyncRepository[TableT, DTOModelT, CUModelT, int],
    Generic[TableT, DTOModelT, CUModelT],
):
    """SQLAlchemy 同步 Repository — 声明式高层 CRUD 接口.

    子类需设置:
        _Table: ORM 模型类
        _DTO: DTO 类
        _session_factory: 返回 Session 的工厂函数
    """

    _Table: ClassVar[type]
    _DTO: ClassVar[type]
    _session_factory: ClassVar[Callable[[], Any]]

    @classmethod
    @contextmanager
    def _get_session(cls) -> Any:
        session = cls._session_factory()  # pyright: ignore[reportAttributeAccessIssue]
        session.expire_on_commit = False
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @classmethod
    def get(cls, pk: int) -> TableT | None:
        """根据主键获取实体."""
        with cls._get_session() as session:
            return session.get(cls._Table, pk)

    @classmethod
    def get_dto(cls, pk: int) -> DTOModelT | None:
        """根据主键获取 DTO."""
        with cls._get_session() as session:
            entity = session.get(cls._Table, pk)
            if entity is None:
                return None
            return cls._DTO.model_validate(entity)

    @classmethod
    def exists(cls, pk: int) -> bool:
        """判断实体是否存在."""
        with cls._get_session() as session:
            return session.get(cls._Table, pk) is not None

    @classmethod
    def count(cls) -> int:
        """统计总数."""
        with cls._get_session() as session:
            stmt = sa.select(sa.func.count()).select_from(cls._Table)
            return session.execute(stmt).scalar() or 0

    @classmethod
    def list(cls, pagination: OffsetPagination | None = None) -> PageResult[DTOModelT]:
        """分页列表 (offset-based)."""
        with cls._get_session() as session:
            stmt = build_offset_stmt(cls._Table, pagination)
            entities = session.execute(stmt).scalars().all()
            items = [cls._DTO.model_validate(e) for e in entities]

            count_stmt = sa.select(sa.func.count()).select_from(cls._Table)
            total = session.execute(count_stmt).scalar() or 0

            return make_page_result(items, total, pagination)

    @classmethod
    def list_cursor(cls, pagination: CursorPagination | None = None) -> CursorResult[DTOModelT]:
        """分页列表 (cursor-based)."""
        p = pagination or CursorPagination()
        with cls._get_session() as session:
            stmt = build_cursor_stmt(cls._Table, pagination)
            entities = session.execute(stmt).scalars().all()
            items = [cls._DTO.model_validate(e) for e in entities]
            return make_cursor_result(items, p.limit)

    @classmethod
    def create(cls, data: CUModelT) -> TableT:
        """创建实体."""
        with cls._get_session() as session:
            entity = data.to_orm_model()
            session.add(entity)
            session.flush()
            session.refresh(entity)
            return entity

    @classmethod
    def update(cls, pk: int, data: CUModelT) -> TableT | None:
        """更新实体 (仅设置非空字段)."""
        with cls._get_session() as session:
            entity = session.get(cls._Table, pk)
            if entity is None:
                return None
            update_fields = data.model_dump(exclude_unset=True, exclude={"id"})
            for key, value in update_fields.items():
                setattr(entity, key, value)
            session.flush()
            session.refresh(entity)
            return entity

    @classmethod
    def delete(cls, pk: int) -> None:
        """删除实体."""
        with cls._get_session() as session:
            entity = session.get(cls._Table, pk)
            if entity is not None:
                session.delete(entity)

    @classmethod
    def bulk_create(cls, items: Iterable[CUModelT]) -> list[TableT]:
        """批量创建."""
        with cls._get_session() as session:
            entities = [item.to_orm_model() for item in items]
            session.add_all(entities)
            session.flush()
            for e in entities:
                session.refresh(e)
            return entities

    @classmethod
    def bulk_update(cls, pks: Iterable[int], data: dict[str, Any]) -> int:
        """批量更新, 返回受影响行数."""
        pk_list = list(pks)
        if not pk_list:
            return 0
        with cls._get_session() as session:
            id_col = cls._Table.id  # pyright: ignore[reportAttributeAccessIssue]
            stmt = sa.update(cls._Table).where(id_col.in_(pk_list)).values(**data)
            result = session.execute(stmt)
            return result.rowcount  # pyright: ignore[reportReturnType]

    @classmethod
    def bulk_delete(cls, pks: Iterable[int]) -> int:
        """批量删除, 返回受影响行数."""
        pk_list = list(pks)
        if not pk_list:
            return 0
        with cls._get_session() as session:
            id_col = cls._Table.id  # pyright: ignore[reportAttributeAccessIssue]
            stmt = sa.delete(cls._Table).where(id_col.in_(pk_list))
            result = session.execute(stmt)
            return result.rowcount  # pyright: ignore[reportReturnType]


class AsyncSQLAlchemyRepository(
    AbstractAsyncRepository[TableT, DTOModelT, CUModelT, int],
    Generic[TableT, DTOModelT, CUModelT],
):
    """SQLAlchemy 异步 Repository — 声明式高层 CRUD 接口.

    子类需设置:
        _Table: ORM 模型类
        _DTO: DTO 类
        _session_factory: 返回 async context manager 的工厂
    """

    _Table: ClassVar[type]
    _DTO: ClassVar[type]
    _session_factory: ClassVar[Callable[..., Any]]

    @classmethod
    async def get(cls, pk: int) -> TableT | None:
        """根据主键获取实体."""
        async with cls._session_factory() as session:
            return await session.get(cls._Table, pk)

    @classmethod
    async def get_dto(cls, pk: int) -> DTOModelT | None:
        """根据主键获取 DTO."""
        async with cls._session_factory() as session:
            entity = await session.get(cls._Table, pk)
            if entity is None:
                return None
            return cls._DTO.model_validate(entity)

    @classmethod
    async def exists(cls, pk: int) -> bool:
        """判断实体是否存在."""
        async with cls._session_factory() as session:
            return (await session.get(cls._Table, pk)) is not None

    @classmethod
    async def count(cls) -> int:
        """统计总数."""
        async with cls._session_factory() as session:
            stmt = sa.select(sa.func.count()).select_from(cls._Table)
            return (await session.execute(stmt)).scalar() or 0

    @classmethod
    async def list(cls, pagination: OffsetPagination | None = None) -> PageResult[DTOModelT]:
        """分页列表 (offset-based)."""
        async with cls._session_factory() as session:
            stmt = build_offset_stmt(cls._Table, pagination)
            result = await session.execute(stmt)
            entities = result.scalars().all()
            items = [cls._DTO.model_validate(e) for e in entities]

            count_stmt = sa.select(sa.func.count()).select_from(cls._Table)
            total = (await session.execute(count_stmt)).scalar() or 0

            return make_page_result(items, total, pagination)

    @classmethod
    async def list_cursor(cls, pagination: CursorPagination | None = None) -> CursorResult[DTOModelT]:
        """分页列表 (cursor-based)."""
        p = pagination or CursorPagination()
        async with cls._session_factory() as session:
            stmt = build_cursor_stmt(cls._Table, pagination)
            result = await session.execute(stmt)
            entities = result.scalars().all()
            items = [cls._DTO.model_validate(e) for e in entities]
            return make_cursor_result(items, p.limit)

    @classmethod
    async def create(cls, data: CUModelT) -> TableT:
        """创建实体."""
        async with cls._session_factory() as session:
            entity = data.to_orm_model()
            session.add(entity)
            await session.flush()
            await session.refresh(entity)
            await session.commit()
            return entity

    @classmethod
    async def update(cls, pk: int, data: CUModelT) -> TableT | None:  # pragma: no cover — async boundary
        """更新实体 (仅设置非空字段)."""
        async with cls._session_factory() as session:
            entity = await session.get(cls._Table, pk)
            if entity is None:
                return None
            update_fields = data.model_dump(exclude_unset=True, exclude={"id"})
            for key, value in update_fields.items():
                setattr(entity, key, value)
            await session.flush()
            await session.refresh(entity)
            await session.commit()
            return entity

    @classmethod
    async def delete(cls, pk: int) -> None:  # pragma: no cover — async boundary
        """删除实体."""
        async with cls._session_factory() as session:
            entity = await session.get(cls._Table, pk)
            if entity is not None:
                await session.delete(entity)
                await session.commit()

    @classmethod
    async def bulk_create(cls, items: Iterable[CUModelT]) -> list[TableT]:  # pragma: no cover — async boundary
        """批量创建."""
        async with cls._session_factory() as session:
            entities = [item.to_orm_model() for item in items]
            session.add_all(entities)
            await session.flush()
            for e in entities:
                await session.refresh(e)
            await session.commit()
            return entities

    @classmethod
    async def bulk_update(cls, pks: Iterable[int], data: dict[str, Any]) -> int:
        """批量更新, 返回受影响行数."""
        pk_list = list(pks)
        if not pk_list:
            return 0
        async with cls._session_factory() as session:
            id_col = cls._Table.id  # pyright: ignore[reportAttributeAccessIssue]
            stmt = sa.update(cls._Table).where(id_col.in_(pk_list)).values(**data)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount  # pyright: ignore[reportReturnType]

    @classmethod
    async def bulk_delete(cls, pks: Iterable[int]) -> int:
        """批量删除, 返回受影响行数."""
        pk_list = list(pks)
        if not pk_list:
            return 0
        async with cls._session_factory() as session:
            id_col = cls._Table.id  # pyright: ignore[reportAttributeAccessIssue]
            stmt = sa.delete(cls._Table).where(id_col.in_(pk_list))
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount  # pyright: ignore[reportReturnType]
