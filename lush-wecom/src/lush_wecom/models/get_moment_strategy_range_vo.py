"""
获取客户朋友圈规则组管理范围模型
"""

from typing import Annotated, Literal

from pydantic import Field

from .common_vo import WeComApiModelBase, WeComBaseResp


class StrategyRangeNode(WeComApiModelBase):
    type: Literal[1, 2]
    userid: str | None = None
    partyid: int | None = None


class GetMomentStrategyRangeRequest(WeComApiModelBase):
    strategy_id: int
    cursor: str | None = None
    limit: Annotated[int | None, Field(le=1000)] = 1000


class GetMomentStrategyRangeResponse(WeComBaseResp):
    range: list[StrategyRangeNode] = Field(default_factory=list)
    next_cursor: str | None = None
