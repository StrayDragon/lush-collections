"""运行时可选依赖检测."""

from __future__ import annotations

_HAS_ASYNC: bool
try:
    from sqlalchemy.ext.asyncio import AsyncSession as _AsyncSession  # noqa: F401

    _HAS_ASYNC = True
except ImportError:  # pragma: no cover
    _HAS_ASYNC = False


def require_async() -> None:
    """当异步支持不可用时立即抛出 ``ImportError``.

    应在依赖 ``sqlalchemy.ext.asyncio`` 的文件 **模块级别** 调用,
    以便用户看到清晰的错误信息而非深层调用栈中的 ``AttributeError``.
    """
    if not _HAS_ASYNC:
        raise ImportError("Async support requires 'sqlalchemy[asyncio]' (greenlet). Install with: pip install 'lush-sqlalchemyx[asyncio]'")
