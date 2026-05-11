"""数据传输对象 (DTO) 与创建/更新 (CU) 模型的 ORM 无关基类.

这些基类只依赖 Pydantic, 不绑定任何具体 ORM.
下游适配包可以通过子类化并绑定 ``_Table`` 来关联具体 ORM 模型.
"""

from __future__ import annotations

import datetime
from typing import Any, ClassVar, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

OrmModelT = TypeVar("OrmModelT")


class BaseCU(BaseModel, Generic[OrmModelT]):
    """创建/更新模型基类.

    子类需设置 ``_Table`` 类变量指向具体 ORM 模型类,
    并实现 ``to_orm_model()`` 返回对应的 ORM 实例.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    _Table: ClassVar[type]  # pyright: ignore[reportGeneralTypeIssues]

    def to_orm_model(self) -> OrmModelT:
        """将 CU 模型转换为 ORM 模型实例.

        默认实现使用 ``model_dump`` 生成字典后传入 ``_Table`` 构造函数.
        子类可覆盖此方法以适配不同 ORM 的构造方式.
        """
        model_data = self.model_dump(exclude_unset=True, exclude={"id"})
        return self._Table(**model_data)


CUModelT = TypeVar("CUModelT", bound=BaseCU[Any])


class BaseDTO(BaseModel, Generic[CUModelT]):
    """数据传输对象基类.

    子类需设置 ``_CU`` 类变量指向对应的 CU 类.
    """

    model_config = ConfigDict(from_attributes=True)

    _CU: ClassVar[type[CUModelT]]  # pyright: ignore[reportGeneralTypeIssues]

    def to_cu(self) -> CUModelT:
        """将 DTO 转换为对应的 CU 模型."""
        return self._CU.model_validate(self)


DTOModelT = TypeVar("DTOModelT", bound=BaseDTO[Any] | BaseModel)


class StdBaseCU(BaseCU[OrmModelT]):
    """标准 CU 基类: 包含创建人/修改人等标准字段."""

    create_operator_id: int = 0
    update_operator_id: int | None = None


class StdBaseDTO(BaseDTO[CUModelT]):
    """标准 DTO 基类: 包含 id、时间戳、操作人等标准字段."""

    id: int = Field(..., description="ID")
    create_datetime: datetime.datetime = Field(..., description="创建时间")
    create_operator_id: int = Field(..., description="创建人")
    update_datetime: datetime.datetime | None = Field(None, description="修改时间")
    update_operator_id: int | None = Field(None, description="修改人")

    model_config = ConfigDict(from_attributes=True)
