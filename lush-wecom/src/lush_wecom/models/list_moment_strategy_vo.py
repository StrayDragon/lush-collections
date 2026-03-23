"""
获取客户朋友圈规则组ID列表模型
"""

from typing import Annotated

from pydantic import Field

from .common_vo import WeComApiModelBase, WeComBaseResp


class ListMomentStrategyRequest(WeComApiModelBase):
    cursor: str | None = None
    limit: Annotated[int | None, Field(le=1000)] = 1000


class ListMomentStrategyItem(WeComApiModelBase):
    strategy_id: int


class ListMomentStrategyResponse(WeComBaseResp):
    strategy: list[ListMomentStrategyItem] = Field(default_factory=list)
    next_cursor: str | None = None
