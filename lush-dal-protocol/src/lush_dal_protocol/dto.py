"""数据传输对象 (DTO) 与创建/更新 (CU) 模型的 ORM 无关基类.

这些基类只依赖 Pydantic, 不绑定任何具体 ORM.
下游适配包可以通过子类化并绑定 ``_Table`` 来关联具体 ORM 模型.
"""

from __future__ import annotations

import datetime
import warnings
from typing import Any, ClassVar, Final, Generic, TypedDict, TypeVar, cast

from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import TypeVar as TypeVarExt

OrmModelT = TypeVar("OrmModelT")


class BaseCUConfigDict(TypedDict, total=False):
    """``BaseCU`` 行为配置 (类似 pydantic ``ConfigDict``).

    推荐写法::

        cu_config = BaseCUConfigDict(to_orm_exclude=frozenset())

    Attributes:
        to_orm_exclude: ``to_orm_model`` / create dump 时排除的字段, 默认 ``frozenset({"id"})``.
        update_exclude: update dump 时排除的字段, 默认 ``frozenset({"id"})``.
    """

    to_orm_exclude: frozenset[str]
    update_exclude: frozenset[str]


# 1:1 水平扩展表 (共享主键) 推荐配置: create 保留 id, update 仍继承排除 id.
EXTEND_TABLE_CU_CONFIG: Final[BaseCUConfigDict] = BaseCUConfigDict(
    to_orm_exclude=frozenset(),
)


class BaseCU(BaseModel, Generic[OrmModelT]):
    """创建/更新模型基类.

    子类需设置 ``_Table`` 类变量指向具体 ORM 模型类,
    并可通过 ``cu_config`` 控制 ``to_orm_model`` / update dump 的排除字段.

    ``cu_config`` 仅在类体中声明; 类创建后再赋值不保证生效.
    子类已设键覆盖上游, 未设键继承上游 (MRO 浅合并, 在 ``__init_subclass__`` 中缓存).
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    _Table: ClassVar[type]

    cu_config: ClassVar[BaseCUConfigDict] = BaseCUConfigDict(
        to_orm_exclude=frozenset({"id"}),
        update_exclude=frozenset({"id"}),
    )
    # BaseCU 自身不触发 __init_subclass__, 需与 cu_config 默认值对齐.
    _resolved_cu_config: ClassVar[BaseCUConfigDict] = BaseCUConfigDict(
        to_orm_exclude=frozenset({"id"}),
        update_exclude=frozenset({"id"}),
    )

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        merged: dict[str, Any] = {}
        for base in reversed(cls.__mro__):
            own = base.__dict__.get("cu_config")
            if own is not None:
                merged.update(own)
        cls._resolved_cu_config = cast("BaseCUConfigDict", merged)

    @classmethod
    def resolve_cu_config(cls) -> BaseCUConfigDict:
        """返回经 MRO 浅合并后的 ``cu_config`` (类创建期已缓存)."""
        return cls._resolved_cu_config

    def to_orm_model(self) -> OrmModelT:
        """将 CU 模型转换为 ORM 模型实例.

        默认实现使用 ``model_dump`` 生成字典后传入 ``_Table`` 构造函数,
        排除字段取自 ``resolve_cu_config()["to_orm_exclude"]``.
        子类可覆盖此方法以适配不同 ORM 的构造方式.
        """
        exclude = type(self)._resolved_cu_config["to_orm_exclude"]
        model_data = self.model_dump(exclude_unset=True, exclude=exclude)
        return self._Table(**model_data)


CUModelT = TypeVarExt("CUModelT", bound=BaseCU[Any], default=BaseCU[Any])


class BaseDTO(BaseModel, Generic[CUModelT]):
    """数据传输对象基类.

    子类需设置 ``_CU`` 类变量指向对应的 CU 类.
    """

    model_config = ConfigDict(from_attributes=True)

    _CU: ClassVar[type[CUModelT]]  # pyright: ignore[reportGeneralTypeIssues]

    def to_cu(self) -> CUModelT:
        """将 DTO 转换为对应的 CU 模型."""
        return self._CU.model_validate(self)


DTOModelT = TypeVarExt("DTOModelT", bound=BaseDTO[Any] | BaseModel, default=BaseModel)


class StdBaseCU(BaseCU[OrmModelT]):
    """标准 CU 基类: 包含创建人/修改人等标准字段.

    .. deprecated::
        此类预设了特定业务字段, 下游应自行继承 ``BaseCU`` 定义所需字段.
    """

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        warnings.warn(
            f"{cls.__name__} 继承了已废弃的 StdBaseCU, 请改为直接继承 BaseCU 并自行定义所需字段",
            DeprecationWarning,
            stacklevel=2,
        )

    create_operator_id: int = 0
    update_operator_id: int | None = None


class StdBaseDTO(BaseDTO[CUModelT]):
    """标准 DTO 基类: 包含 id、时间戳、操作人等标准字段.

    .. deprecated::
        此类预设了特定业务字段, 下游应自行继承 ``BaseDTO`` 定义所需字段.
    """

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        warnings.warn(
            f"{cls.__name__} 继承了已废弃的 StdBaseDTO, 请改为直接继承 BaseDTO 并自行定义所需字段",
            DeprecationWarning,
            stacklevel=2,
        )

    id: int = Field(..., description="ID")
    create_datetime: datetime.datetime = Field(..., description="创建时间")
    create_operator_id: int = Field(..., description="创建人")
    update_datetime: datetime.datetime | None = Field(None, description="修改时间")
    update_operator_id: int | None = Field(None, description="修改人")

    model_config = ConfigDict(from_attributes=True)
