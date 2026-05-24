"""组合 ABC 层 — 提供常用的 Read + Write 组合."""

from __future__ import annotations

from abc import ABC
from typing import Generic

from lush_dal_protocol.abc._types import EntityT, PrimaryKeyT, SessionT
from lush_dal_protocol.abc.read import AbstractAsyncReadDAL, AbstractSyncReadDAL
from lush_dal_protocol.abc.write import AbstractAsyncWriteDAL, AbstractSyncWriteDAL
from lush_dal_protocol.dto import CUModelT, DTOModelT
from lush_dal_protocol.params.extra import ExtraT


class AbstractSyncBaseDAL(
    AbstractSyncReadDAL[SessionT, EntityT, DTOModelT, PrimaryKeyT, ExtraT],
    AbstractSyncWriteDAL[SessionT, EntityT, DTOModelT, CUModelT, PrimaryKeyT, ExtraT],
    ABC,
    Generic[SessionT, EntityT, DTOModelT, CUModelT, PrimaryKeyT, ExtraT],
):
    """同步完整 CRUD DAL 抽象基类 (Read + Write)."""


class AbstractAsyncBaseDAL(
    AbstractAsyncReadDAL[SessionT, EntityT, DTOModelT, PrimaryKeyT, ExtraT],
    AbstractAsyncWriteDAL[SessionT, EntityT, DTOModelT, CUModelT, PrimaryKeyT, ExtraT],
    ABC,
    Generic[SessionT, EntityT, DTOModelT, CUModelT, PrimaryKeyT, ExtraT],
):
    """异步完整 CRUD DAL 抽象基类 (Read + Write)."""
