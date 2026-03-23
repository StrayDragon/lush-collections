"""
创建客户朋友圈规则组模型
"""

from pydantic import Field

from .common_vo import WeComApiModelBase, WeComBaseResp
from .get_moment_strategy_range_vo import StrategyRangeNode
from .get_moment_strategy_vo import MomentStrategyPrivilege


class CreateMomentStrategyRequest(WeComApiModelBase):
    strategy_name: str
    admin_list: list[str] = Field(default_factory=list)
    range: list[StrategyRangeNode] = Field(default_factory=list)
    parent_id: int | None = None
    privilege: MomentStrategyPrivilege | None = None


class CreateMomentStrategyResponse(WeComBaseResp):
    strategy_id: int | None = None
