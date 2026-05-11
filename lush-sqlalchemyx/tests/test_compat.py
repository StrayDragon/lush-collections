"""Tests for _compat module."""

import importlib
from unittest.mock import patch

import pytest

from lush_sqlalchemyx._compat import _HAS_ASYNC, require_async


def test_has_async_is_true():
    assert _HAS_ASYNC is True


def test_require_async_passes():
    require_async()


def test_require_async_fails_when_no_async():
    import lush_sqlalchemyx._compat as compat_mod

    original = compat_mod._HAS_ASYNC
    try:
        compat_mod._HAS_ASYNC = False
        with pytest.raises(ImportError, match="sqlalchemy\\[asyncio\\]"):
            compat_mod.require_async()
    finally:
        compat_mod._HAS_ASYNC = original


def test_has_async_false_on_import_error():
    """Simulate the ImportError branch."""
    import lush_sqlalchemyx._compat as compat_mod

    with patch.dict("sys.modules", {"sqlalchemy.ext.asyncio": None}):
        original = compat_mod._HAS_ASYNC
        compat_mod._HAS_ASYNC = False
        try:
            with pytest.raises(ImportError, match="sqlalchemy\\[asyncio\\]"):
                compat_mod.require_async()
        finally:
            compat_mod._HAS_ASYNC = original
