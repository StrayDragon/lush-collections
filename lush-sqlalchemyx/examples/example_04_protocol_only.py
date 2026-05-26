"""场景 04: 直接使用 lush-dal-protocol BaseCU — ORM 无关场景.

当下游不需要 SQLAlchemy 特有功能时, 可直接使用 protocol 层的 BaseCU.
验证 protocol 层和 sqlalchemyx 层的 BaseCU 可以共存而不冲突.
"""

from typing import ClassVar

from lush_dal_protocol.dto import BaseCU as ProtocolBaseCU
from lush_dal_protocol.dto import BaseDTO as ProtocolBaseDTO

# ---------------------------------------------------------------------------
# 非 ORM 模型 (如内存映射、外部 API 响应)
# ---------------------------------------------------------------------------


class ExternalAPIUser:
    """模拟非 ORM 模型 — 不继承任何 SQLAlchemy 基类."""

    def __init__(self, name: str, email: str) -> None:
        self.name = name
        self.email = email


# ---------------------------------------------------------------------------
# CU / DTO — 纯 Pydantic, 不依赖 SQLAlchemy
# ---------------------------------------------------------------------------


class ExternalUserCU(ProtocolBaseCU["ExternalAPIUser"]):
    _Table: ClassVar[type] = ExternalAPIUser

    name: str
    email: str


class ExternalUserDTO(ProtocolBaseDTO[ExternalUserCU]):
    _CU: ClassVar[type[ExternalUserCU]] = ExternalUserCU

    name: str
    email: str
