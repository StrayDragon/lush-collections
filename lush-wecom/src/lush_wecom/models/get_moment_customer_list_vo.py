"""
获取客户朋友圈可见客户列表模型
"""

from typing import Annotated

from pydantic import Field

from .common_vo import WeComApiModelBase, WeComBaseResp


class GetMomentCustomerListRequest(WeComApiModelBase):
    moment_id: str
    userid: str
    cursor: str | None = None
    limit: Annotated[int | None, Field(le=1000)] = 500


class GetMomentCustomerListItem(WeComApiModelBase):
    userid: str
    external_userid: str


class GetMomentCustomerListResponse(WeComBaseResp):
    next_cursor: str | None = None
    customer_list: list[GetMomentCustomerListItem] = Field(default_factory=list)
