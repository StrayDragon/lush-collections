"""示例 3: 实现 Repository ABC.

展示如何继承 lush-dal-protocol 的 Repository 抽象基类
来实现自定义的数据访问层.

注意: 此示例使用内存实现, 实际使用时需要绑定到具体 ORM (如 SQLAlchemy).
"""

from collections.abc import Iterable
from typing import Any, ClassVar

from lush_dal_protocol.dto import BaseCU, BaseDTO
from lush_dal_protocol.params.pagination import CursorPagination, CursorResult, OffsetPagination, PageResult
from lush_dal_protocol.repository import AbstractAsyncRepository, AbstractSyncRepository

# 场景 1: 同步 Repository 实现 (内存)


class InMemoryUser:
    """模拟用户实体."""

    def __init__(self, id: int, name: str, email: str | None = None) -> None:
        self.id = id
        self.name = name
        self.email = email


class UserCU(BaseCU[InMemoryUser]):
    """用户 Create/Update 模型."""

    _Table: ClassVar[type] = InMemoryUser
    name: str
    email: str | None = None


class UserDTO(BaseDTO[UserCU]):
    """用户 DTO."""

    _CU: ClassVar[type[UserCU]] = UserCU
    id: int
    name: str
    email: str | None = None


class InMemoryUserRepository(AbstractSyncRepository[InMemoryUser, UserDTO, UserCU, int]):
    """内存实现的同步用户 Repository (示例用, 实际应使用真实 ORM)."""

    _storage: ClassVar[dict[int, InMemoryUser]] = {}
    _next_id: ClassVar[int] = 1

    @classmethod
    def get(cls, pk: int) -> InMemoryUser | None:
        return cls._storage.get(pk)

    @classmethod
    def get_dto(cls, pk: int) -> UserDTO | None:
        entity = cls.get(pk)
        if entity is None:
            return None
        return UserDTO(id=entity.id, name=entity.name, email=entity.email)

    @classmethod
    def exists(cls, pk: int) -> bool:
        return pk in cls._storage

    @classmethod
    def count(cls) -> int:
        return len(cls._storage)

    @classmethod
    def list(cls, pagination: OffsetPagination | None = None) -> PageResult[UserDTO]:
        p = pagination or OffsetPagination()
        all_items = list(cls._storage.values())
        start = p.skip
        end = start + p.limit
        items = all_items[start:end]
        dtos = [UserDTO(id=item.id, name=item.name, email=item.email) for item in items]
        return PageResult[UserDTO](
            items=dtos,
            total=len(all_items),
            skip=p.skip,
            limit=p.limit,
        )

    @classmethod
    def list_cursor(cls, pagination: CursorPagination | None = None) -> CursorResult[UserDTO]:
        p = pagination or CursorPagination()
        all_items = sorted(cls._storage.values(), key=lambda x: x.id)
        items = all_items[: p.limit]
        dtos = [UserDTO(id=item.id, name=item.name, email=item.email) for item in items]
        next_cursor = str(items[-1].id) if items else None
        return CursorResult[UserDTO](items=dtos, next_cursor=next_cursor)

    @classmethod
    def create(cls, data: UserCU) -> InMemoryUser:
        entity = InMemoryUser(
            id=cls._next_id,
            name=data.name,
            email=data.email,
        )
        cls._storage[entity.id] = entity
        cls._next_id += 1
        return entity

    @classmethod
    def update(cls, pk: int, data: UserCU) -> InMemoryUser | None:
        entity = cls._storage.get(pk)
        if entity is None:
            return None
        if data.name is not None:
            entity.name = data.name
        if data.email is not None:
            entity.email = data.email
        return entity

    @classmethod
    def delete(cls, pk: int) -> None:
        cls._storage.pop(pk, None)

    @classmethod
    def bulk_create(cls, items: Iterable[UserCU]) -> list[InMemoryUser]:
        result = []
        for item in items:
            entity = cls.create(item)
            result.append(entity)
        return result

    @classmethod
    def bulk_update(cls, pks: Iterable[int], data: dict[str, Any]) -> int:
        count = 0
        for pk in pks:
            entity = cls._storage.get(pk)
            if entity is not None:
                for key, value in data.items():
                    setattr(entity, key, value)
                count += 1
        return count

    @classmethod
    def bulk_delete(cls, pks: Iterable[int]) -> int:
        count = 0
        for pk in pks:
            if pk in cls._storage:
                del cls._storage[pk]
                count += 1
        return count


# 场景 2: 异步 Repository 实现 (占位)


class AsyncInMemoryUserRepository(AbstractAsyncRepository[InMemoryUser, UserDTO, UserCU, int]):
    """内存实现的异步用户 Repository (示例占位)."""

    @classmethod
    async def get(cls, pk: int) -> InMemoryUser | None:
        return InMemoryUserRepository.get(pk)

    @classmethod
    async def get_dto(cls, pk: int) -> UserDTO | None:
        return InMemoryUserRepository.get_dto(pk)

    @classmethod
    async def exists(cls, pk: int) -> bool:
        return InMemoryUserRepository.exists(pk)

    @classmethod
    async def count(cls) -> int:
        return InMemoryUserRepository.count()

    @classmethod
    async def list(cls, pagination: OffsetPagination | None = None) -> PageResult[UserDTO]:
        return InMemoryUserRepository.list(pagination)

    @classmethod
    async def list_cursor(cls, pagination: CursorPagination | None = None) -> CursorResult[UserDTO]:
        return InMemoryUserRepository.list_cursor(pagination)

    @classmethod
    async def create(cls, data: UserCU) -> InMemoryUser:
        return InMemoryUserRepository.create(data)

    @classmethod
    async def update(cls, pk: int, data: UserCU) -> InMemoryUser | None:
        return InMemoryUserRepository.update(pk, data)

    @classmethod
    async def delete(cls, pk: int) -> None:
        InMemoryUserRepository.delete(pk)

    @classmethod
    async def bulk_create(cls, items: Iterable[UserCU]) -> list[InMemoryUser]:
        return InMemoryUserRepository.bulk_create(items)

    @classmethod
    async def bulk_update(cls, pks: Iterable[int], data: dict[str, Any]) -> int:
        return InMemoryUserRepository.bulk_update(pks, data)

    @classmethod
    async def bulk_delete(cls, pks: Iterable[int]) -> int:
        return InMemoryUserRepository.bulk_delete(pks)


# 场景 3: 使用示例


def _verify_repository_usage() -> None:
    """验证 Repository 类型推断正确."""

    # 创建
    cu = UserCU(name="Alice", email="alice@example.com")
    entity = InMemoryUserRepository.create(cu)
    assert entity.id == 1
    assert entity.name == "Alice"

    # 读取
    dto = InMemoryUserRepository.get_dto(1)
    assert dto is not None
    assert dto.name == "Alice"

    # 更新
    updated = InMemoryUserRepository.update(1, UserCU(name="Alice Updated"))
    assert updated is not None
    assert updated.name == "Alice Updated"

    # 删除
    InMemoryUserRepository.delete(1)
    assert not InMemoryUserRepository.exists(1)
