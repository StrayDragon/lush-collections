"""
企业微信通用模型定义
"""

from pydantic import BaseModel, ConfigDict, Field


class WeComApiModelBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class WeComBaseResp(WeComApiModelBase):
    errcode: int = Field(default=-1, description="错误码,0表示成功")
    errmsg: str = Field(default="err-default", description="错误信息")


class GetAccessTokenResp(WeComBaseResp):
    access_token: str | None = Field(None, description="获取到的凭证")
    expires_in: int | None = Field(None, description="凭证的有效时间(秒)")
