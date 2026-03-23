"""
删除客户朋友圈规则组模型
"""

from .common_vo import WeComApiModelBase, WeComBaseResp


class DeleteMomentStrategyRequest(WeComApiModelBase):
    strategy_id: int


class DeleteMomentStrategyResponse(WeComBaseResp):
    """删除客户朋友圈规则组响应"""
