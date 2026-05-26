"""场景 01: 纯 SQLAlchemy 同步表 — SyncSqlATableBase + BaseCU/BaseDTO + SyncDAL V2."""

from typing import ClassVar

from sqlalchemy.orm import Mapped, mapped_column

from lush_sqlalchemyx.base.dal import (
    BaseCU,
    BaseDTO,
    BasicSyncBaseTable,
    SyncBaseDALV2,
)

# ---------------------------------------------------------------------------
# Table
# ---------------------------------------------------------------------------


class User(BasicSyncBaseTable):
    """同步用户表."""

    __tablename__ = "example_user"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column()
    email: Mapped[str | None] = mapped_column(default=None)


# ---------------------------------------------------------------------------
# CU / DTO
# ---------------------------------------------------------------------------


class UserCU(BaseCU["User"]):
    _Table: ClassVar[type] = User

    name: str
    email: str | None = None


class UserDTO(BaseDTO[UserCU]):
    _CU: ClassVar[type[UserCU]] = UserCU

    id: int
    name: str
    email: str | None = None


# ---------------------------------------------------------------------------
# DAL V2
# ---------------------------------------------------------------------------


class UserDAL(SyncBaseDALV2[User, UserDTO, UserCU]):
    """用户 DAL — 验证 SyncBaseDALV2 泛型参数解析."""
