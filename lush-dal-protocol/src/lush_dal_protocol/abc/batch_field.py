"""批量字段查询 ABC 层."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from typing import Any, Generic, TypeVar

from lush_dal_protocol.abc._types import EntityT, SessionT
from lush_dal_protocol.dto import DTOModelT

T = TypeVar("T")


class AbstractSyncBatchFieldDAL(ABC, Generic[SessionT, EntityT, DTOModelT]):
    """同步批量字段查询 DAL 抽象基类."""

    @classmethod
    @abstractmethod
    def batch_get_field__entity(
        cls,
        session: SessionT,
        *,
        field_name: str,
        field_values: Iterable[T],
        field_value_type_as: Callable[[T], T] = lambda x: x,
    ) -> dict[Any, EntityT]:
        """按指定字段批量获取实体, 返回 {field_value: entity} 字典."""
        ...

    @classmethod
    @abstractmethod
    def batch_get_field__dto(
        cls,
        session: SessionT,
        *,
        field_name: str,
        field_values: Iterable[T],
    ) -> dict[Any, DTOModelT]:
        """按指定字段批量获取 DTO, 返回 {field_value: DTO} 字典."""
        ...


class AbstractAsyncBatchFieldDAL(ABC, Generic[SessionT, EntityT, DTOModelT]):
    """异步批量字段查询 DAL 抽象基类.

    语义与 ``AbstractSyncBatchFieldDAL`` 一致, 所有方法为 ``async def``.
    """

    @classmethod
    @abstractmethod
    async def batch_get_field__entity(
        cls,
        session: SessionT,
        *,
        field_name: str,
        field_values: Iterable[T],
        field_value_type_as: Callable[[T], T] = lambda x: x,
    ) -> dict[Any, EntityT]:
        """按指定字段批量获取实体, 返回 {field_value: entity} 字典."""
        ...

    @classmethod
    @abstractmethod
    async def batch_get_field__dto(
        cls,
        session: SessionT,
        *,
        field_name: str,
        field_values: Iterable[T],
    ) -> dict[Any, DTOModelT]:
        """按指定字段批量获取 DTO, 返回 {field_value: DTO} 字典."""
        ...
