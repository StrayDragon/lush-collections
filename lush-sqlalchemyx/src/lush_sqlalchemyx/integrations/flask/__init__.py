"""Flask-SQLAlchemy 可选集成.

需要安装 ``flask`` 额外依赖:  ``pip install lush-sqlalchemyx[flask]``
"""

from .ext import LushFlaskSQLAlchemy, MySQLManagerMapperFlaskDepends

__all__ = ["LushFlaskSQLAlchemy", "MySQLManagerMapperFlaskDepends"]
