"""示例 1: 使用 BaseCU/BaseDTO 创建自定义 DTO.

展示如何继承 lush-dal_protocol 的 DTO 基类来创建类型安全的 Create/Update 和读取模型.
"""

from typing import ClassVar

from lush_dal_protocol.dto import BaseCU, BaseDTO, StdBaseCU

# 场景 1: 标准用法 — 使用 StdBaseCU (包含 id, created_at, updated_at)


class UserTable:
    """模拟 ORM 表类 (非实际 ORM, 仅用于类型标注)."""

    def __init__(self, id: int, name: str, email: str | None = None) -> None:
        self.id = id
        self.name = name
        self.email = email


class UserStdCU(StdBaseCU[UserTable]):
    """标准 Create/Update 模型 — 包含 id, created_at, updated_at 字段."""

    _Table: ClassVar[type] = UserTable
    name: str
    email: str | None = None


class UserStdDTO(BaseDTO[UserStdCU]):
    """标准 DTO — 继承 CU 所有字段."""

    _CU: ClassVar[type[UserStdCU]] = UserStdCU
    id: int
    name: str
    email: str | None = None


# 场景 2: 简化用法 — 使用 BaseCU (不包含标准字段)


class UserSimpleCU(BaseCU[UserTable]):
    """简化 Create/Update 模型 — 仅包含业务字段."""

    _Table: ClassVar[type] = UserTable
    name: str
    email: str | None = None


class UserSimpleDTO(BaseDTO[UserSimpleCU]):
    """简化 DTO — 不包含 id/时间戳."""

    _CU: ClassVar[type[UserSimpleCU]] = UserSimpleCU
    name: str
    email: str | None = None


# 场景 3: 带额外字段的 DTO


class UserExtendedDTO(BaseDTO[UserStdCU]):
    """扩展 DTO — 添加计算字段."""

    _CU: ClassVar[type[UserStdCU]] = UserStdCU
    id: int
    name: str
    email: str | None = None
    # 计算字段 (不存在于 CU 中)
    display_name: str | None = None


# 类型检查验证
def _verify_dto_types() -> None:
    """验证 DTO 类型推断正确."""

    # StdBaseCU 用法
    cu_std = UserStdCU(name="Alice", email="alice@example.com")
    assert cu_std.model_dump(exclude_unset=True) == {"name": "Alice", "email": "alice@example.com"}

    # BaseCU 用法
    cu_simple = UserSimpleCU(name="Bob")
    assert cu_simple.name == "Bob"

    # DTO 验证
    dto = UserStdDTO(id=1, name="Charlie", email="charlie@example.com")
    assert dto.id == 1
    assert dto.name == "Charlie"
