"""下游用户类型检查 SSOT — 模拟真实使用场景, 由 basedpyright 作为门禁验证.

每个子模块覆盖一种下游框架/ORM 的集成模式:
  01: 纯 SQLAlchemy 同步 (SyncSqlATableBase)
  02: 纯 SQLAlchemy 异步 (AsyncSqlATableBase)
  03: Flask-SQLAlchemy (db.Model, 静态类型不可见 DeclarativeBase 继承链)
  04: lush-dal-protocol 直接使用 (ORM 无关)

如果 bound 被误加回 DeclarativeBase, 03 场景会报 reportInvalidTypeArguments.
"""
