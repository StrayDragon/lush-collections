"""
获取客户朋友圈规则组详情模型
"""

from pydantic import Field

from .common_vo import WeComApiModelBase, WeComBaseResp


class MomentStrategyPrivilege(WeComApiModelBase):
    view_moment_list: bool | None = True
    send_moment: bool | None = True
    manage_moment_cover_and_sign: bool | None = True


class MomentStrategyDetail(WeComApiModelBase):
    strategy_id: int
    parent_id: int
    strategy_name: str
    create_time: int
    admin_list: list[str] = Field(default_factory=list)
    privilege: MomentStrategyPrivilege | None = None


class GetMomentStrategyRequest(WeComApiModelBase):
    strategy_id: int


class GetMomentStrategyResponse(WeComBaseResp):
    strategy: MomentStrategyDetail | None = None
