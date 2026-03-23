"""
获取朋友圈发表任务结果模型
"""

from enum import IntEnum
from typing import Annotated

from pydantic import Field

from .common_vo import WeComApiModelBase, WeComBaseResp


class MomentTaskPollStatus(IntEnum):
    """企微朋友圈任务轮询状态码

    参考文档: https://developer.work.weixin.qq.com/document/path/95094
    """

    CREATING = 1  # 开始创建
    IN_PROGRESS = 2  # 创建中
    COMPLETED = 3  # 创建完成


class GetMomentTaskResultRequest(WeComApiModelBase):
    jobid: str


class GetMomentTaskResultInvalidSender(WeComApiModelBase):
    user_list: list[str] = Field(default_factory=list)
    department_list: list[int] = Field(default_factory=list)


class GetMomentTaskResultInvalidExternalContact(WeComApiModelBase):
    tag_list: list[str] = Field(default_factory=list)


class GetMomentTaskResultDetail(WeComApiModelBase):
    errcode: int
    errmsg: str
    moment_id: str | None = None
    invalid_sender_list: GetMomentTaskResultInvalidSender | None = None
    invalid_external_contact_list: GetMomentTaskResultInvalidExternalContact | None = None


class GetMomentTaskResultResponse(WeComBaseResp):
    status: Annotated[int | None, Field(description="1-开始创建,2-创建中,3-创建完成")] = None
    type: Annotated[str | None, Field(description="任务类型,固定 add_moment_task")] = None
    result: GetMomentTaskResultDetail | None = None
