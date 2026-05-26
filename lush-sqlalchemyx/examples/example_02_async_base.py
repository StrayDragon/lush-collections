"""场景 02: 纯 SQLAlchemy 异步表 — AsyncSqlATableBase + BaseCU/BaseDTO + AsyncDAL V2."""

from typing import ClassVar

from sqlalchemy.orm import Mapped, mapped_column

from lush_sqlalchemyx.base.dal import (
    AsyncBaseDALV2,
    BaseCU,
    BaseDTO,
    BasicAsyncBaseTable,
)

# ---------------------------------------------------------------------------
# Table
# ---------------------------------------------------------------------------


class Order(BasicAsyncBaseTable):
    """异步订单表."""

    __tablename__ = "example_order"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column()
    amount: Mapped[int] = mapped_column(default=0)


# ---------------------------------------------------------------------------
# CU / DTO
# ---------------------------------------------------------------------------


class OrderCU(BaseCU["Order"]):
    _Table: ClassVar[type] = Order

    title: str
    amount: int = 0


class OrderDTO(BaseDTO[OrderCU]):
    _CU: ClassVar[type[OrderCU]] = OrderCU

    id: int
    title: str
    amount: int


# ---------------------------------------------------------------------------
# DAL V2
# ---------------------------------------------------------------------------


class OrderDAL(AsyncBaseDALV2[Order, OrderDTO, OrderCU]):
    """订单 DAL — 验证 AsyncBaseDALV2 泛型参数解析."""
