import dataclasses
import enum
from typing import Any

from pydantic import GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import ValidationError as PydanticValidationError
from pydantic_core import core_schema
from typing_extensions import Self


@dataclasses.dataclass(frozen=True, slots=True)
class XMetaInfo:
    description: str = ""
    display_text: str = ""


class MetaInfoIntEnum(enum.IntEnum):
    """
    带有 XMetaInfo 的 IntEnum

    行为与 IntEnum 基本一致, 可通过 ``.x_meta`` 获取预定义的 XMetaInfo。

    基本用法:

    .. code-block:: python

        class OrderStatus(MetaInfoIntEnum):
            PENDING = 1, XMetaInfo("待支付")
            PAID = 2, XMetaInfo("已支付")


        status = OrderStatus.PAID
        print(status.x_meta.description)  # "已支付"

    扩展 XMetaInfo (推荐):

    .. code-block:: python

        @dataclass(frozen=True, slots=True)
        class PaymentMeta(XMetaInfo):
            color: str = ""
            icon: str = ""


        class PaymentMethod(MetaInfoIntEnum):
            _x_meta: PaymentMeta  # pyright: ignore[reportIncompatibleVariableOverride,reportUninitializedInstanceVariable]

            WECHAT = 1, PaymentMeta("微信支付", color="#07c160", icon="💚")
            ALIPAY = 2, PaymentMeta("支付宝", color="#1677ff", icon="💙")


        pm = PaymentMethod.WECHAT
        print(pm.x_meta.color)  # 运行时 .x_meta 返回 PaymentMeta
        print(pm._x_meta.color)  # 类型检查时用 ._x_meta (仅需 reportPrivateUsage suppress)

    应用级中间基类:

    .. code-block:: python

        class AppIntEnum(MetaInfoIntEnum):
            _x_meta: PaymentMeta  # pyright: ignore[reportIncompatibleVariableOverride,reportUninitializedInstanceVariable]


        class RefundReason(AppIntEnum):
            QUALITY = 1, PaymentMeta("质量问题", color="#ff0000", icon="🔴")
    """

    _x_meta: XMetaInfo  # pyright: ignore[reportUninitializedInstanceVariable]

    def __init_subclass__(cls, **kwargs: object) -> None:
        """当子类声明了更窄的 _x_meta 类型时, 自动生成窄化的 x_meta property."""
        super().__init_subclass__(**kwargs)
        if "_x_meta" in cls.__annotations__:
            xm_type = cls.__annotations__["_x_meta"]
            if xm_type is not XMetaInfo:
                # 自动生成窄化的 x_meta property, 运行时 .x_meta 返回子类声明的类型
                cls.x_meta = property(lambda self, _t=xm_type: self._x_meta)

    def __new__(cls, value: int, meta: XMetaInfo) -> Self:
        obj = int.__new__(cls, value)
        obj._value_ = value
        obj._x_meta = meta
        return obj

    @classmethod
    def to_db_field_comment(cls) -> str:
        return " ".join([f"{i.value}: {i._x_meta.description}" for i in cls])

    @property
    def x_meta(self) -> XMetaInfo:
        return self._x_meta

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: Any) -> core_schema.CoreSchema:
        base_schema = handler(source_type)

        def wrap_validator(value: Any, validator: core_schema.ValidatorFunctionWrapHandler) -> enum.Enum:
            if isinstance(value, cls):
                return validator(value)

            original_value = value

            if isinstance(value, str):
                try:
                    value = int(value)
                except (ValueError, TypeError) as exc:
                    raise ValueError(f"'{original_value}' is not a valid member of {cls.__name__}") from exc

            try:
                return validator(value)
            except (PydanticValidationError, TypeError, ValueError) as exc:
                raise ValueError(f"'{original_value}' is not a valid value for {cls.__name__}") from exc

        schema = core_schema.no_info_wrap_validator_function(wrap_validator, base_schema)
        schema["serialization"] = core_schema.plain_serializer_function_ser_schema(lambda x: x.value if hasattr(x, "value") else x)
        return schema

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)

        descriptions = [f"* `{member.value}`: {member._x_meta.description}" for member in cls]
        schema_description = "枚举值:\n\n" + "\n".join(descriptions)

        # 为 MetaInfoIntEnum 明确设置为 integer 类型(不支持 string)
        json_schema.update(
            type="integer",
            description=schema_description,
            enum=[member.value for member in cls],
            **{
                "x-enum-module": cls.__module__,
                "x-enum-class": cls.__qualname__,
            },
        )
        return json_schema


class MetaInfoStrEnum(str, enum.Enum):
    """
    带有 XMetaInfo 的 StrEnum

    行为与 StrEnum 基本一致, 可通过 ``.x_meta`` 获取预定义的 XMetaInfo。

    继承与扩展用法同 :class:`MetaInfoIntEnum`。
    """

    _x_meta: XMetaInfo

    def __init_subclass__(cls, **kwargs: object) -> None:
        """当子类声明了更窄的 _x_meta 类型时, 自动生成窄化的 x_meta property."""
        super().__init_subclass__(**kwargs)
        if "_x_meta" in cls.__annotations__:
            xm_type = cls.__annotations__["_x_meta"]
            if xm_type is not XMetaInfo:
                # 自动生成窄化的 x_meta property, 运行时 .x_meta 返回子类声明的类型
                cls.x_meta = property(lambda self, _t=xm_type: self._x_meta)

    def __new__(cls, value: str, meta: XMetaInfo) -> Self:
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj._x_meta = meta
        return obj

    def __str__(self) -> str:  # pyright: ignore[reportImplicitOverride]
        return self.value

    @classmethod
    def to_db_field_comment(cls) -> str:
        return " ".join([f"{i.value}: {i._x_meta.description}" for i in cls])

    @property
    def x_meta(self) -> XMetaInfo:
        return self._x_meta

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: Any) -> core_schema.CoreSchema:
        base_schema = handler(source_type)

        def wrap_validator(value: Any, validator: core_schema.ValidatorFunctionWrapHandler) -> enum.Enum:
            if isinstance(value, cls):
                return validator(value)

            if isinstance(value, str):
                try:
                    return validator(cls(value))
                except ValueError:
                    try:
                        member = cls[value.upper()]
                    except KeyError as exc:
                        raise ValueError(f"'{value}' is not a valid value or name for {cls.__name__}") from exc
                    return validator(member)

            raise ValueError(f"Input for {cls.__name__} must be a string.")

        schema = core_schema.no_info_wrap_validator_function(wrap_validator, base_schema)
        schema["serialization"] = core_schema.plain_serializer_function_ser_schema(lambda x: x.value if hasattr(x, "value") else x)
        return schema

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)

        descriptions = [f"* `{member.value}`: {member._x_meta.description}" for member in cls]
        schema_description = "枚举值:\n\n" + "\n".join(descriptions)

        # 为 MetaInfoStrEnum 明确设置为 string 类型
        json_schema.update(
            type="string",
            description=schema_description,
            enum=[member.value for member in cls],
            **{
                "x-enum-module": cls.__module__,
                "x-enum-class": cls.__qualname__,
            },
        )
        return json_schema


class EnumField:
    """
    EnumField 是一个描述符字段, 用于校验和序列化枚举值。

    它会自动将值转换为对应的枚举成员, 可通过 ._x_meta 获取预定义的 XMetaInfo
    """

    def __init__(self, enum_cls: type[enum.Enum]) -> None:
        if not issubclass(enum_cls, enum.Enum):
            raise TypeError("enum_cls must be subclass of enum.Enum")
        self.enum_cls = enum_cls
        self.private_name = None

    def __set_name__(self, owner: Any, name: str) -> None:
        self.private_name = f"_{name}"

    def __get__(self, instance: Any, owner: Any) -> Any:
        if instance is None:
            return self
        if self.private_name is None:
            return None
        return getattr(instance, self.private_name, None)

    def __set__(self, instance: Any, value: Any) -> None:
        if value is None:
            setattr(instance, self.private_name, None)  # pyright: ignore[reportArgumentType]
            return

        try:
            member = self.enum_cls(value)
        except ValueError:
            try:
                if not isinstance(value, str):
                    raise KeyError  # noqa: TRY301
                member = self.enum_cls[value.upper()]
            except KeyError:
                raise ValueError(f"'{value}' is not a valid member, value or name for {self.enum_cls.__name__}") from None

        setattr(instance, self.private_name, member)  # pyright: ignore[reportArgumentType]
