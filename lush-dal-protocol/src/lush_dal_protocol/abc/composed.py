"""组合 ABC 层 — 提供常用的 Read + Write 组合."""

from __future__ import annotations

from typing import Generic

from lush_dal_protocol.abc._types import EntityT, SessionT
from lush_dal_protocol.abc.read import AbstractAsyncReadDAL, AbstractSyncReadDAL
from lush_dal_protocol.abc.write import AbstractAsyncWriteDAL, AbstractSyncWriteDAL
from lush_dal_protocol.dto import CUModelT, DTOModelT


class AbstractSyncBaseDAL(
    AbstractSyncReadDAL[SessionT, EntityT, DTOModelT],
    AbstractSyncWriteDAL[SessionT, EntityT, DTOModelT, CUModelT],
    Generic[SessionT, EntityT, DTOModelT, CUModelT],
):
    """同步完整 CRUD DAL 抽象基类 (Read + Write)."""


class AbstractAsyncBaseDAL(
    AbstractAsyncReadDAL[SessionT, EntityT, DTOModelT],
    AbstractAsyncWriteDAL[SessionT, EntityT, DTOModelT, CUModelT],
    Generic[SessionT, EntityT, DTOModelT, CUModelT],
):
    """异步完整 CRUD DAL 抽象基类 (Read + Write)."""
