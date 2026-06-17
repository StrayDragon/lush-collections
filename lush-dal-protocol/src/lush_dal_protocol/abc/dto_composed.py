"""组合 Dto 协议 — 提供无 EntityT 的 Read + Write 组合."""

from __future__ import annotations

from abc import ABC
from typing import Generic

from pydantic import BaseModel
from typing_extensions import TypeVar as TypeVarExt

from ._types import PrimaryKeyT, SessionT
from .dto_read import DtoAsyncReadDAL, DtoSyncReadDAL
from .dto_write import DtoAsyncWriteDAL, DtoSyncWriteDAL

CUModelT = TypeVarExt("CUModelT", bound=BaseModel, default=BaseModel)
DTOModelT = TypeVarExt("DTOModelT", bound=BaseModel, default=BaseModel)


class DtoSyncDAL(
    DtoSyncReadDAL[SessionT, DTOModelT, PrimaryKeyT],
    DtoSyncWriteDAL[SessionT, DTOModelT, CUModelT, PrimaryKeyT],
    ABC,
    Generic[SessionT, DTOModelT, CUModelT, PrimaryKeyT],
):
    """同步完整 CRUD DAL 协议 (Read + Write), 无 EntityT."""


class DtoAsyncDAL(
    DtoAsyncReadDAL[SessionT, DTOModelT, PrimaryKeyT],
    DtoAsyncWriteDAL[SessionT, DTOModelT, CUModelT, PrimaryKeyT],
    ABC,
    Generic[SessionT, DTOModelT, CUModelT, PrimaryKeyT],
):
    """异步完整 CRUD DAL 协议 (Read + Write), 无 EntityT."""
