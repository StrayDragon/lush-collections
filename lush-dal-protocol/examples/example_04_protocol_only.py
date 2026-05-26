"""示例 4: 仅使用协议类型 (不依赖具体 ORM).

展示如何使用 lush-dal-protocol 的类型定义
而不依赖任何具体 ORM 实现 (如 SQLAlchemy, Django ORM).

适用于:
- 跨不同 ORM 的抽象层
- 不使用传统 ORM 的场景 (如 NoSQL、API 客户端)
- 需要类型安全但运行时动态的场景.
"""

from dataclasses import dataclass
from typing import Any, ClassVar, TypeVar

from lush_dal_protocol.dto import BaseCU, BaseDTO

# 场景 1: 不使用 ORM 的纯数据类


@dataclass
class PlainUser:
    """普通 dataclass, 不继承任何 ORM 基类."""

    id: int
    name: str
    email: str | None = None


class PlainUserCU(BaseCU[PlainUser]):
    """即使 PlainUser 不是 ORM 类, BaseCU 仍然可用."""

    _Table: ClassVar[type] = PlainUser
    name: str
    email: str | None = None

    def to_orm_model(self) -> PlainUser:
        """自定义 ORM 模型创建逻辑."""
        return PlainUser(
            id=0,  # 占位, 实际由数据库分配
            name=self.name,
            email=self.email,
        )


class PlainUserDTO(BaseDTO[PlainUserCU]):
    """DTO 仍然可以正常工作."""

    _CU: ClassVar[type[PlainUserCU]] = PlainUserCU
    id: int
    name: str
    email: str | None = None


# 场景 2: 泛型函数 (Python 3.10 语法)


EntityT = TypeVar("EntityT")
CUModelT = TypeVar("CUModelT", bound=BaseCU[Any])


def process_entity(cu: CUModelT) -> Any:
    """泛型函数处理任意 CU 类型, 不关心具体 ORM."""
    return cu.to_orm_model()


def _verify_protocol_only_usage() -> None:
    """验证纯协议用法."""

    # PlainUserCU 用法
    cu = PlainUserCU(name="Bob", email="bob@example.com")
    entity = cu.to_orm_model()
    assert entity.name == "Bob"
    assert entity.email == "bob@example.com"

    # 泛型函数
    result = process_entity(cu)
    assert result is entity

    # DTO 用法
    dto = PlainUserDTO(id=1, name="Bob", email="bob@example.com")
    assert dto.name == "Bob"
