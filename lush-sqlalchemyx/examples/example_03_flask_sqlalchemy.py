"""场景 03: Flask-SQLAlchemy db.Model — 触发 bound 问题的原始场景.

Flask-SQLAlchemy 的 db.Model 运行时继承 DeclarativeBase,
但静态类型系统看不到该继承链.  如果 SQLATableT 被加回 bound=DeclarativeBase,
此文件的 BaseCU["UserBillBaseInfo"] 会报 reportInvalidTypeArguments.
"""

from datetime import datetime
from typing import ClassVar

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

from lush_sqlalchemyx.base.dal import BaseCU, BaseDTO

# ---------------------------------------------------------------------------
# Flask app + db (最小化, 仅用于类型检查)
# ---------------------------------------------------------------------------

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
db = SQLAlchemy(app)


# ---------------------------------------------------------------------------
# Table — 模拟下游 Flask-SQLAlchemy 用户定义
# ---------------------------------------------------------------------------


class UserBillBaseInfo(db.Model):
    """模拟下游真实模型: 继承 db.Model 而非 DeclarativeBase."""

    __tablename__ = "user_bill_base_info"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)  # type: ignore[assignment]
    user_id = db.Column(db.BigInteger, nullable=False, unique=True, index=True)  # type: ignore[assignment]
    name = db.Column(db.String(100), nullable=False)  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# CU / DTO — 验证 BaseCU[非 DeclarativeBase 类型] 不报错
# ---------------------------------------------------------------------------


class BaseInfoCU(BaseCU["UserBillBaseInfo"]):
    _Table: ClassVar[type] = UserBillBaseInfo

    user_id: int
    name: str


class BaseInfoDTO(BaseDTO[BaseInfoCU]):
    _CU: ClassVar[type[BaseInfoCU]] = BaseInfoCU

    id: int
    user_id: int
    name: str
    create_datetime: datetime | None = None
