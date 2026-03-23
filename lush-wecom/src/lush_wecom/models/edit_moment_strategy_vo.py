"""
编辑客户朋友圈规则组模型
"""

from .common_vo import WeComApiModelBase, WeComBaseResp
from .get_moment_strategy_range_vo import StrategyRangeNode
from .get_moment_strategy_vo import MomentStrategyPrivilege


class EditMomentStrategyRequest(WeComApiModelBase):
    strategy_id: int
    strategy_name: str | None = None
    admin_list: list[str] | None = None
    privilege: MomentStrategyPrivilege | None = None
    range_add: list[StrategyRangeNode] | None = None
    range_del: list[StrategyRangeNode] | None = None


class EditMomentStrategyResponse(WeComBaseResp):
    """编辑客户朋友圈规则组响应"""
