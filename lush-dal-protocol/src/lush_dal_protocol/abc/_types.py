"""ABC 层共享的泛型参数定义."""

from __future__ import annotations

from typing import TypeVar

from typing_extensions import TypeVar as TypeVarExt

SessionT = TypeVar("SessionT")
EntityT = TypeVar("EntityT")
PrimaryKeyT = TypeVarExt("PrimaryKeyT", default=int)
