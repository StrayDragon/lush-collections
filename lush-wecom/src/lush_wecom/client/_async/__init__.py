"""
企业微信SDK - 异步版本

特性:
- 使用 httpx.AsyncClient 进行异步 HTTP 调用
- 使用 AnyIO 进行异步文件 I/O 与路径操作
- 与同步版 API 对齐: 方法名与返回模型保持一致,仅需 await 调用
"""

# region imports

import contextlib
import logging
import os
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path as SyncPath
from typing import Literal, TypeVar, cast
from urllib.parse import urlparse

import anyio
import httpx

from lush_wecom.core.base import AsyncWeComClientBase
from lush_wecom.core.const import (
    DEFAULT_CHUNK_SIZE,
    FILE_SIZE_LIMITS,
    AttachmentTypeLiteral,
)
from lush_wecom.models import (
    add_moment_task_vo,
    add_msg_template_vo,
    auth_get_user_detail_vo,
    auth_get_user_info_vo,
    cancel_groupmsg_send_vo,
    cancel_moment_task_vo,
    common_vo,
    create_moment_strategy_vo,
    delete_moment_strategy_vo,
    edit_moment_strategy_vo,
    get_groupmsg_list_vo,
    get_groupmsg_send_result_vo,
    get_groupmsg_task_vo,
    get_moment_comments_vo,
    get_moment_customer_list_vo,
    get_moment_list_vo,
    get_moment_send_result_vo,
    get_moment_strategy_range_vo,
    get_moment_strategy_vo,
    get_moment_task_result_vo,
    get_moment_task_vo,
    list_moment_strategy_vo,
    media_vo,
    recall_app_message_vo,
    remind_groupmsg_send_vo,
    send_app_message_vo,
    update_template_card_vo,
    upload_attachment_media_vo,
    upload_image_vo,
    upload_temporary_media_vo,
)
from lush_wecom.utils.media_validators import check_moment_image_resolution, ensure_attachment_upload_constraints

# endregion


logger = logging.getLogger(__name__)

T = TypeVar("T", bound=common_vo.WeComBaseResp)


class AsyncWeComClient(AsyncWeComClientBase):
    """统一异步企业微信客户端"""

    # ===== 应用消息API =====
    async def send_app_message(self, payload: send_app_message_vo.SendAppMessageRequest) -> send_app_message_vo.SendAppMessageResponse:
        """
        发送应用消息
        参考文档: https://developer.work.weixin.qq.com/document/path/90236

        支持的消息类型:
        - 文本消息 (text)
        - 图片消息 (image)
        - 语音消息 (voice)
        - 视频消息 (video)
        - 文件消息 (file)
        - 文本卡片消息 (textcard)
        - 图文消息 (news)
        - 图文消息(mpnews) (mpnews)
        - markdown消息 (markdown)
        - 小程序通知消息 (miniprogram_notice)
        - 模板卡片消息 (template_card)

        注意事项:
        - touser、toparty、totag不能同时为空
        - 频率限制: 每应用不可超过账号上限数*200人次/天
        - 每应用对同一个成员不可超过30次/分钟, 1000次/小时
        """
        endpoint = "/message/send"
        json_payload = payload.model_dump(exclude_none=True)
        return await self._make_request("POST", endpoint, send_app_message_vo.SendAppMessageResponse, json=json_payload)

    async def update_template_card(
        self, payload: update_template_card_vo.UpdateTemplateCardRequest
    ) -> update_template_card_vo.UpdateTemplateCardResponse:
        """
        更新模板卡片消息
        参考文档: https://developer.work.weixin.qq.com/document/path/94888

        功能说明:
        - 应用发送模板卡片消息后,可以更新可回调的用户任务卡片消息的替换文案信息
        - 仅原卡片为按钮交互型、投票选择型、多项选择型的卡片以及填写了action_menu字段的文本通知型、图文展示型可以调用本接口更新
        - response_code的有效期是72小时,超过72小时后将无法使用
        - 一个response_code只能调用一次该接口

        支持的更新方式:
        1. 更新按钮为不可点击状态: 仅原卡片为按钮交互型、投票选择型、多项选择型的卡片可以更新按钮
        2. 更新为新的卡片: 可回调的卡片可以更新成任何一种模板卡片

        注意事项:
        - userids、partyids、tagids、atall不能同时为空
        - response_code通过发送模板卡片消息接口或回调接口返回值获取
        - 如果部分指定的用户无权限或不存在,更新仍然执行,但会返回无效的部分
        """
        endpoint = "/message/update_template_card"
        json_payload = payload.model_dump(exclude_none=True)
        return await self._make_request("POST", endpoint, update_template_card_vo.UpdateTemplateCardResponse, json=json_payload)

    async def recall_app_message(
        self, payload: recall_app_message_vo.RecallAppMessageRequest
    ) -> recall_app_message_vo.RecallAppMessageResponse:
        """
        撤回应用消息
        参考文档: https://developer.work.weixin.qq.com/document/path/94867

        功能说明:
        - 本接口可以撤回24小时内通过发送应用消息接口推送的消息
        - 仅可撤回企业微信端的数据,微信插件端的数据不支持撤回

        注意事项:
        - msgid是从应用发送消息接口处获得的消息ID
        - 只能撤回24小时内发送的消息
        - 撤回操作不可逆
        """
        endpoint = "/message/recall"
        json_payload = payload.model_dump(exclude_none=True)
        return await self._make_request("POST", endpoint, recall_app_message_vo.RecallAppMessageResponse, json=json_payload)

    # ===== 网页授权登录API =====
    async def auth_get_user_info(self, code: str) -> auth_get_user_info_vo.GetUserInfoResponse:
        """
        获取访问用户身份
        参考文档: https://developer.work.weixin.qq.com/document/path/91023

        功能说明:
        - 根据code获取成员信息,适用于自建应用与代开发应用
        - code只能使用一次,5分钟未被使用自动过期
        - 跳转的域名须完全匹配access_token对应应用的可信域名

        返回结果说明:
        a) 当用户为企业成员时(无论是否在应用可见范围之内):
           - userid: 成员UserID
           - user_ticket: 成员票据(scope为snsapi_privateinfo且用户在应用可见范围内时返回)

        b) 非企业成员时:
           - openid: 非企业成员的标识
           - external_userid: 外部联系人id(用户是企业客户且跟进人在应用可见范围内时返回)

        Args:
            code: 通过成员授权获取到的code,最大为512字节

        Returns:
            auth_get_user_info_vo.GetUserInfoResponse: 用户身份信息
        """
        endpoint = "/auth/getuserinfo"
        params = {"code": code}
        return await self._make_request("GET", endpoint, auth_get_user_info_vo.GetUserInfoResponse, params=params)

    async def auth_get_user_detail(self, user_ticket: str) -> auth_get_user_detail_vo.GetUserDetailResponse:
        """
        获取访问用户敏感信息
        参考文档: https://developer.work.weixin.qq.com/document/path/95833

        功能说明:
        - 通过user_ticket获取用户的敏感信息(如手机号、邮箱等)
        - user_ticket有效期为1800s
        - 仅在scope为snsapi_privateinfo且用户在应用可见范围内时可用

        Args:
            user_ticket: 成员票据,从auth_get_user_info接口获取

        Returns:
            auth_get_user_detail_vo.GetUserDetailResponse: 用户详细信息
        """
        endpoint = "/auth/getuserdetail"
        json_payload = {"user_ticket": user_ticket}
        return await self._make_request("POST", endpoint, auth_get_user_detail_vo.GetUserDetailResponse, json=json_payload)

    # ===== 外部联系人群发API =====
    async def add_msg_template(self, payload: add_msg_template_vo.AddMsgTemplateRequest) -> add_msg_template_vo.AddMsgTemplateResponse:
        """
        创建企业群发
        参考文档: https://developer.work.weixin.qq.com/document/path/92135
        """
        endpoint = "/externalcontact/add_msg_template"
        json_payload = payload.model_dump(exclude_none=True)
        return await self._make_request("POST", endpoint, add_msg_template_vo.AddMsgTemplateResponse, json=json_payload)

    async def remind_groupmsg_send(
        self, payload: remind_groupmsg_send_vo.RemindGroupMsgSendRequest
    ) -> remind_groupmsg_send_vo.RemindGroupMsgSendResponse:
        """
        提醒企业群发
        参考文档: https://developer.work.weixin.qq.com/document/path/97611
        """
        endpoint = "/externalcontact/remind_groupmsg_send"
        json_payload = payload.model_dump(exclude_none=True)
        return await self._make_request(
            "POST",
            endpoint,
            remind_groupmsg_send_vo.RemindGroupMsgSendResponse,
            json=json_payload,
        )

    async def cancel_groupmsg_send(
        self, payload: cancel_groupmsg_send_vo.CancelGroupMsgSendRequest
    ) -> cancel_groupmsg_send_vo.CancelGroupMsgSendResponse:
        """
        停止企业群发
        参考文档: https://developer.work.weixin.qq.com/document/path/97611
        """
        endpoint = "/externalcontact/cancel_groupmsg_send"
        json_payload = payload.model_dump(exclude_none=True)
        return await self._make_request(
            "POST",
            endpoint,
            cancel_groupmsg_send_vo.CancelGroupMsgSendResponse,
            json=json_payload,
        )

    async def get_groupmsg_list(self, payload: get_groupmsg_list_vo.GetGroupMsgListRequest) -> get_groupmsg_list_vo.GetGroupMsgListResponse:
        """
        获取群发记录列表
        参考文档: https://developer.work.weixin.qq.com/document/path/93338

        NOTE:
        - 调用过`停止企业群发`停止的群发消息(msgid), 不能通过以下返回看出来被停发, 得请求`获取群发成员发送任务列表`来查看状态


        参考返回:
        ```json
        {
          "errcode": 0,
          "errmsg": "ok",
          "next_cursor": "",
          "group_msg_list": [
            {
              "msgid": "MSG_ID",
              "create_time": 1754029871,
              "create_type": 0,
              "text": {
                "content": "test, 测试"
              },
              "attachments": [
                {
                  "msgtype": "image",
                  "image": {
                    "media_id": "MEDIA_ID"
                  }
                },
                {
	                  "msgtype": "link",
	                  "link": {
	                    "title": "示例链接(网页端)",
	                    "url": "https://example.com/",
	                    "picurl": "https://example.com/static/cover.png",
	                    "desc": "示例描述: 一个普通的链接卡片"
	                  }
	                },
	                {
	                  "msgtype": "miniprogram",
	                  "miniprogram": {
	                    "title": "示例小程序",
	                    "appid": "wx1234567890abcdef",
	                    "page": "pages/index/index"
	                  }
	                }
	              ]
	            }
	          ]
        }
        ```
        """
        endpoint = "/externalcontact/get_groupmsg_list_v2"
        json_payload = payload.model_dump(exclude_none=True)
        return await self._make_request("POST", endpoint, get_groupmsg_list_vo.GetGroupMsgListResponse, json=json_payload)

    async def get_groupmsg_task(self, payload: get_groupmsg_task_vo.GetGroupMsgTaskRequest) -> get_groupmsg_task_vo.GetGroupMsgTaskResponse:
        """
        获取群发成员发送任务列表
        参考文档: https://developer.work.weixin.qq.com/document/path/93338

        参考返回:
        ```json
        {
          "errcode": 0,
          "errmsg": "ok",
          "next_cursor": "",
          "task_list": [{"userid": "contumacy", "status": 2, "send_time": 1754029889}]
        }
        ```

        NOTE: 已取消的群发任务调用这个会报错
        ```json
        {
          "errcode": 41093,
          "errmsg": "group message canceled",
          "...": "...",
        }
        ```
        """
        endpoint = "/externalcontact/get_groupmsg_task"
        json_payload = payload.model_dump(exclude_none=True)
        return await self._make_request("POST", endpoint, get_groupmsg_task_vo.GetGroupMsgTaskResponse, json=json_payload)

    async def get_groupmsg_send_result(
        self, payload: get_groupmsg_send_result_vo.GetGroupMsgSendResultRequest
    ) -> get_groupmsg_send_result_vo.GetGroupMsgSendResultResponse:
        """
        获取企业群发成员执行结果
        参考文档: https://developer.work.weixin.qq.com/document/path/93338

        参考返回:
        ```json
        {
          "errcode": 0,
          "errmsg": "ok",
          "next_cursor": "",
          "send_list": [
            {
              "external_userid": "wm8XPdCwAAv_zQiZ886ROYlTPyzr9xmA",
              "userid": "contumacy",
              "status": 1,
              "send_time": 1754029889
            }
          ]
        }
        ```
        """
        endpoint = "/externalcontact/get_groupmsg_send_result"
        json_payload = payload.model_dump(exclude_none=True)
        return await self._make_request("POST", endpoint, get_groupmsg_send_result_vo.GetGroupMsgSendResultResponse, json=json_payload)

    # region 客户朋友圈API
    async def add_moment_task(self, payload: add_moment_task_vo.AddMomentTaskRequest) -> add_moment_task_vo.AddMomentTaskResponse:
        """
        创建发表任务
        创建客户朋友圈发表任务
        参考文档: https://developer.work.weixin.qq.com/document/path/95094
        """
        endpoint = "/externalcontact/add_moment_task"
        json_payload = payload.model_dump(exclude_none=True)
        return await self._make_request("POST", endpoint, add_moment_task_vo.AddMomentTaskResponse, json=json_payload)

    async def get_moment_task_result(
        self, payload: get_moment_task_result_vo.GetMomentTaskResultRequest
    ) -> get_moment_task_result_vo.GetMomentTaskResultResponse:
        """
        获取任务创建结果
        查询朋友圈发表任务创建结果
        参考文档: https://developer.work.weixin.qq.com/document/path/95094
        """
        endpoint = "/externalcontact/get_moment_task_result"
        params = payload.model_dump(exclude_none=True)
        return await self._make_request("GET", endpoint, get_moment_task_result_vo.GetMomentTaskResultResponse, params=params)

    async def cancel_moment_task(
        self, payload: cancel_moment_task_vo.CancelMomentTaskRequest
    ) -> cancel_moment_task_vo.CancelMomentTaskResponse:
        """
        停止尚未发送的企业朋友圈任务
        参考文档: https://developer.work.weixin.qq.com/document/path/97612
        """
        endpoint = "/externalcontact/cancel_moment_task"
        json_payload = payload.model_dump(exclude_none=True)
        return await self._make_request(
            "POST",
            endpoint,
            cancel_moment_task_vo.CancelMomentTaskResponse,
            json=json_payload,
        )

    async def get_moment_list(self, payload: get_moment_list_vo.GetMomentListRequest) -> get_moment_list_vo.GetMomentListResponse:
        """
        获取企业全部的客户朋友圈发表记录
        参考文档: https://developer.work.weixin.qq.com/document/path/93333
        """
        endpoint = "/externalcontact/get_moment_list"
        json_payload = payload.model_dump(exclude_none=True)
        return await self._make_request("POST", endpoint, get_moment_list_vo.GetMomentListResponse, json=json_payload)

    async def get_moment_task(self, payload: get_moment_task_vo.GetMomentTaskRequest) -> get_moment_task_vo.GetMomentTaskResponse:
        """
        获取企业发表的朋友圈成员执行情况
        参考文档: https://developer.work.weixin.qq.com/document/path/93333
        """
        endpoint = "/externalcontact/get_moment_task"
        json_payload = payload.model_dump(exclude_none=True)
        return await self._make_request("POST", endpoint, get_moment_task_vo.GetMomentTaskResponse, json=json_payload)

    async def get_moment_customer_list(
        self, payload: get_moment_customer_list_vo.GetMomentCustomerListRequest
    ) -> get_moment_customer_list_vo.GetMomentCustomerListResponse:
        """
        获取客户朋友圈发表时选择的可见客户列表
        参考文档: https://developer.work.weixin.qq.com/document/path/93333
        """
        endpoint = "/externalcontact/get_moment_customer_list"
        json_payload = payload.model_dump(exclude_none=True)
        return await self._make_request("POST", endpoint, get_moment_customer_list_vo.GetMomentCustomerListResponse, json=json_payload)

    async def get_moment_send_result(
        self, payload: get_moment_send_result_vo.GetMomentSendResultRequest
    ) -> get_moment_send_result_vo.GetMomentSendResultResponse:
        """
        获取客户朋友圈发表后的可见客户列表
        参考文档: https://developer.work.weixin.qq.com/document/path/93333
        """
        endpoint = "/externalcontact/get_moment_send_result"
        json_payload = payload.model_dump(exclude_none=True)
        return await self._make_request("POST", endpoint, get_moment_send_result_vo.GetMomentSendResultResponse, json=json_payload)

    async def get_moment_comments(
        self, payload: get_moment_comments_vo.GetMomentCommentsRequest
    ) -> get_moment_comments_vo.GetMomentCommentsResponse:
        """
        获取客户朋友圈的互动数据
        参考文档: https://developer.work.weixin.qq.com/document/path/93333
        """
        endpoint = "/externalcontact/get_moment_comments"
        json_payload = payload.model_dump(exclude_none=True)
        return await self._make_request("POST", endpoint, get_moment_comments_vo.GetMomentCommentsResponse, json=json_payload)

    async def list_moment_strategies(
        self, payload: list_moment_strategy_vo.ListMomentStrategyRequest
    ) -> list_moment_strategy_vo.ListMomentStrategyResponse:
        """
        获取客户朋友圈规则组ID列表
        参考文档: https://developer.work.weixin.qq.com/document/path/94890
        """
        endpoint = "/externalcontact/moment_strategy/list"
        json_payload = payload.model_dump(exclude_none=True)
        return await self._make_request("POST", endpoint, list_moment_strategy_vo.ListMomentStrategyResponse, json=json_payload)

    async def get_moment_strategy(
        self, payload: get_moment_strategy_vo.GetMomentStrategyRequest
    ) -> get_moment_strategy_vo.GetMomentStrategyResponse:
        """
        获取客户朋友圈规则组详情
        参考文档: https://developer.work.weixin.qq.com/document/path/94890
        """
        endpoint = "/externalcontact/moment_strategy/get"
        json_payload = payload.model_dump(exclude_none=True)
        return await self._make_request("POST", endpoint, get_moment_strategy_vo.GetMomentStrategyResponse, json=json_payload)

    async def get_moment_strategy_range(
        self, payload: get_moment_strategy_range_vo.GetMomentStrategyRangeRequest
    ) -> get_moment_strategy_range_vo.GetMomentStrategyRangeResponse:
        """
        获取客户朋友圈规则组管理范围
        参考文档: https://developer.work.weixin.qq.com/document/path/94890
        """
        endpoint = "/externalcontact/moment_strategy/get_range"
        json_payload = payload.model_dump(exclude_none=True)
        return await self._make_request("POST", endpoint, get_moment_strategy_range_vo.GetMomentStrategyRangeResponse, json=json_payload)

    async def create_moment_strategy(
        self, payload: create_moment_strategy_vo.CreateMomentStrategyRequest
    ) -> create_moment_strategy_vo.CreateMomentStrategyResponse:
        """
        创建新的客户朋友圈规则组
        参考文档: https://developer.work.weixin.qq.com/document/path/94890
        """
        endpoint = "/externalcontact/moment_strategy/create"
        json_payload = payload.model_dump(exclude_none=True)
        return await self._make_request("POST", endpoint, create_moment_strategy_vo.CreateMomentStrategyResponse, json=json_payload)

    async def edit_moment_strategy(
        self, payload: edit_moment_strategy_vo.EditMomentStrategyRequest
    ) -> edit_moment_strategy_vo.EditMomentStrategyResponse:
        """
        编辑客户朋友圈规则组及其管理范围
        参考文档: https://developer.work.weixin.qq.com/document/path/94890
        """
        endpoint = "/externalcontact/moment_strategy/edit"
        json_payload = payload.model_dump(exclude_none=True)
        return await self._make_request(
            "POST",
            endpoint,
            edit_moment_strategy_vo.EditMomentStrategyResponse,
            json=json_payload,
        )

    async def delete_moment_strategy(
        self, payload: delete_moment_strategy_vo.DeleteMomentStrategyRequest
    ) -> delete_moment_strategy_vo.DeleteMomentStrategyResponse:
        """
        删除客户朋友圈规则组
        参考文档: https://developer.work.weixin.qq.com/document/path/94890
        """
        endpoint = "/externalcontact/moment_strategy/del"
        json_payload = payload.model_dump(exclude_none=True)
        return await self._make_request(
            "POST",
            endpoint,
            delete_moment_strategy_vo.DeleteMomentStrategyResponse,
            json=json_payload,
        )

    # endregion

    # ===== 媒体API =====
    async def upload_temporary_media(self, file_path: str, media_type: str) -> upload_temporary_media_vo.UploadTemporaryMediaResponse:
        """
        上传临时素材文件到企业微信
        参考文档: https://developer.work.weixin.qq.com/document/path/90253
        """
        path = anyio.Path(file_path)
        if not await path.exists():
            raise FileNotFoundError(f"文件未找到: {file_path}")

        file_stat = await path.stat()
        if file_stat.st_size <= 5:
            raise ValueError("文件大小必须大于5个字节")

        valid_types = ["image", "voice", "video", "file"]
        if media_type not in valid_types:
            raise ValueError(f"无效的 media_type '{media_type}'必须是 {valid_types} 中的一个")

        endpoint = "/media/upload"
        params = {"type": media_type}

        # 使用 AnyIO 异步读取文件内容并以内存方式上传
        data = await path.read_bytes()
        files = {"media": (SyncPath(file_path).name, data)}
        return await self._make_request(
            "POST",
            endpoint,
            upload_temporary_media_vo.UploadTemporaryMediaResponse,
            params=params,
            files=files,
        )

    async def upload_attachment_media(
        self,
        file_path: str,
        media_type: Literal["image", "video", "file"],
        attachment_type: AttachmentTypeLiteral,
    ) -> upload_attachment_media_vo.UploadAttachmentMediaResponse:
        """
        上传附件资源,用于朋友圈或商品图册
        参考文档: https://developer.work.weixin.qq.com/document/path/95098

        注意:
        - 朋友圈附件(attachment_type=1)仅支持 image/video
        - 商品图册附件(attachment_type=2)仅支持 image
        - 所有文件需大于5字节,且大小不超过10MB
        - 朋友圈图片分辨率要求: 长边不超过10800像素, 短边不超过1080像素
        """
        path = anyio.Path(file_path)
        if not await path.exists():
            raise FileNotFoundError(f"文件未找到: {file_path}")

        file_stat = await path.stat()
        normalized_media_type = ensure_attachment_upload_constraints(media_type, attachment_type, file_stat.st_size)

        # 朋友圈图片分辨率检查
        if attachment_type == 1 and normalized_media_type == "image":
            _ = check_moment_image_resolution(file_path)

        endpoint = "/media/upload_attachment"
        params = {
            "media_type": normalized_media_type,
            "attachment_type": attachment_type,
        }
        data = await path.read_bytes()
        files = {"media": (SyncPath(file_path).name, data)}
        return await self._make_request(
            "POST",
            endpoint,
            upload_attachment_media_vo.UploadAttachmentMediaResponse,
            params=params,
            files=files,
        )

    async def upload_attachment_media_from_url(
        self,
        media_url: str,
        media_type: Literal["image", "video", "file"],
        attachment_type: AttachmentTypeLiteral,
    ) -> upload_attachment_media_vo.UploadAttachmentMediaResponse:
        """
        从URL下载文件后上传为附件资源
        参考文档: https://developer.work.weixin.qq.com/document/path/95098

        Args:
            media_url: 远程文件URL
            media_type: 媒体类型(image/video/file)
            attachment_type: 附件类型(1:朋友圈,2:商品图册)
        """
        temp_path: str | None = None
        try:
            download_result = await self._download_media_from_url(media_url)
            temp_path = download_result.temp_file_path
            normalized_media_type = cast(
                "Literal['image', 'video', 'file']",
                ensure_attachment_upload_constraints(
                    media_type,
                    attachment_type,
                    download_result.file_size,
                ),
            )
            return await self.upload_attachment_media(temp_path, normalized_media_type, attachment_type)
        finally:
            if temp_path:
                p = anyio.Path(temp_path)
                with contextlib.suppress(Exception):
                    await p.unlink(missing_ok=True)

    async def upload_image(self, image_path: str) -> upload_image_vo.UploadImageResponse:
        """
        上传图片到企业微信以获取一个永久有效的URL
        参考文档: https://developer.work.weixin.qq.com/document/path/90256
        """
        path = anyio.Path(image_path)
        if not await path.exists():
            raise FileNotFoundError(f"图片文件未找到: {image_path}")

        file_stat = await path.stat()
        max_size = FILE_SIZE_LIMITS["upload_image"]
        if not (5 < file_stat.st_size <= max_size):
            max_size_mb = max_size // (1024 * 1024)
            raise ValueError(f"图片文件大小必须在 5 字节到 {max_size_mb}MB 之间")

        endpoint = "/media/uploadimg"
        data = await path.read_bytes()
        files = {"media": (SyncPath(image_path).name, data)}
        return await self._make_request("POST", endpoint, upload_image_vo.UploadImageResponse, files=files)

    async def _download_media_from_url(self, media_url: str) -> media_vo.MediaDownloadResult:
        """
        从URL下载媒体文件到临时文件

        Args:
            media_url: 媒体文件的URL

        Returns:
            media_vo.MediaDownloadResult: 包含临时文件路径、文件名、content_type和文件大小的结果对象

        Raises:
            ValueError: 当URL无效或下载失败时
            httpx.RequestError: 网络请求错误
        """
        if not media_url or not media_url.strip():
            raise ValueError("媒体文件URL不能为空")

        async with httpx.AsyncClient() as client:
            try:
                head_response = await client.head(media_url, timeout=10, follow_redirects=True)
                _ = head_response.raise_for_status()

                parsed_url = urlparse(media_url)
                original_filename = SyncPath(parsed_url.path).name or "media_file"
                content_type = str(head_response.headers.get("content-type", "application/octet-stream")).lower()

                if "." not in original_filename:
                    if "image" in content_type:
                        if "jpeg" in content_type or "jpg" in content_type:
                            original_filename += ".jpg"
                        elif "png" in content_type:
                            original_filename += ".png"
                        elif "gif" in content_type:
                            original_filename += ".gif"
                        elif "webp" in content_type:
                            original_filename += ".webp"
                        else:
                            original_filename += ".jpg"
                    elif "video" in content_type:
                        if "mp4" in content_type:
                            original_filename += ".mp4"
                        else:
                            original_filename += ".mp4"
                    elif "audio" in content_type:
                        if "amr" in content_type:
                            original_filename += ".amr"
                        else:
                            original_filename += ".amr"
                    elif not original_filename.endswith(".txt"):
                        original_filename += ".bin"

                temp_fd, temp_path = tempfile.mkstemp(suffix=f"_{original_filename}")
                with contextlib.suppress(OSError):
                    os.close(temp_fd)

                file_size = 0
                try:
                    async with client.stream("GET", media_url, timeout=30) as response:
                        _ = response.raise_for_status()
                        async with await anyio.open_file(temp_path, "wb") as temp_file:
                            async for chunk in response.aiter_bytes(chunk_size=8192):
                                file_size += len(chunk)
                                _ = await temp_file.write(chunk)

                    return media_vo.MediaDownloadResult(
                        temp_file_path=temp_path,
                        filename=original_filename,
                        content_type=content_type,
                        file_size=file_size,
                    )
                except Exception:
                    p = anyio.Path(temp_path)
                    if await p.exists():
                        with contextlib.suppress(Exception):
                            await p.unlink(missing_ok=True)
                    raise
            except httpx.RequestError as e:
                raise ValueError(f"下载媒体文件失败: {e}") from e

    async def upload_temporary_media_from_url(
        self, media_url: str, media_type: str
    ) -> upload_temporary_media_vo.UploadTemporaryMediaResponse:
        """
        从URL下载媒体文件并上传为临时素材到企业微信

        Args:
            media_url: 媒体文件的URL
            media_type: 媒体类型,必须是 "image", "voice", "video", "file" 中的一个

        Returns:
            media_vo.TemporaryMediaResponse: 上传响应,包含 media_id

        Raises:
            ValueError: 当URL无效、media_type无效或文件大小不符合要求时
            FileNotFoundError: 当下载失败时
        """
        temp_path: str | None = None
        try:
            download_result = await self._download_media_from_url(media_url)
            temp_path = download_result.temp_file_path
            file_size = download_result.file_size

            size_limits = FILE_SIZE_LIMITS
            if media_type not in size_limits:
                raise ValueError(f"无效的 media_type '{media_type}'")
            if file_size > size_limits[media_type]:
                max_size = size_limits[media_type] // (1024 * 1024)
                raise ValueError(f"{media_type} 文件大小不能超过 {max_size}MB")

            return await self.upload_temporary_media(temp_path, media_type)
        finally:
            if temp_path:
                p = anyio.Path(temp_path)
                with contextlib.suppress(Exception):
                    await p.unlink(missing_ok=True)

    async def upload_image_from_url(self, image_url: str) -> upload_image_vo.UploadImageResponse:
        """
        从URL下载图片并上传到企业微信以获取一个永久有效的URL

        Args:
            image_url: 图片文件的URL

        Returns:
            media_vo.ImageUploadResponse: 上传响应,包含永久有效的图片URL

        Raises:
            ValueError: 当URL无效或文件大小不符合要求时
            FileNotFoundError: 当下载失败时
        """
        temp_path: str | None = None
        try:
            download_result = await self._download_media_from_url(image_url)
            temp_path = download_result.temp_file_path
            content_type = download_result.content_type
            file_size = download_result.file_size

            if not (5 < file_size <= FILE_SIZE_LIMITS["upload_image"]):
                max_size_mb = FILE_SIZE_LIMITS["upload_image"] // (1024 * 1024)
                raise ValueError(f"图片文件大小必须在 5 字节到 {max_size_mb}MB 之间")

            if not content_type.lower().startswith("image/"):
                raise ValueError(f"文件类型必须是图片,当前类型: {content_type}")

            return await self.upload_image(temp_path)
        finally:
            if temp_path:
                p = anyio.Path(temp_path)
                with contextlib.suppress(Exception):
                    await p.unlink(missing_ok=True)

    # ===== 媒体下载(流式) =====
    async def get_temporary_media(self, media_id: str, chunk_size: int = DEFAULT_CHUNK_SIZE) -> AsyncIterator[bytes]:
        """
        根据media_id获取临时素材文件

        注意:
        1. 此方法直接返回文件流,不经过Pydantic解析,需要特殊处理
        2. 超过20M的文件需要使用Range分块下载,否则返回错误码830002
        3. media_id有效期只有3天

        Args:
            media_id: 媒体文件ID
            chunk_size: 分块大小,默认20MB(建议不超过20MB)

        Returns:
            文件流迭代器

        参考文档: https://developer.work.weixin.qq.com/document/path/90254
        """
        return self._make_stream_request(
            method="GET",
            endpoint="/media/get",
            chunk_size=chunk_size,
            params={"media_id": media_id},
        )

    async def get_temporary_media_with_range(
        self,
        media_id: str,
        start_byte: int = 0,
        end_byte: int | None = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ) -> AsyncIterator[bytes]:
        """
        根据media_id获取临时素材文件(支持断点下载)

        Args:
            media_id: 媒体文件ID
            start_byte: 起始字节位置
            end_byte: 结束字节位置,None表示到文件末尾
            chunk_size: 分块大小,默认20MB

        Returns:
            文件流迭代器

        例子:
            # 下载文件的前1024字节
            stream = client.get_temporary_media_with_range("MEDIA_ID", 0, 1023)

            # 从1024字节开始下载到末尾
            stream = client.get_temporary_media_with_range("MEDIA_ID", 1024)

        参考文档: https://developer.work.weixin.qq.com/document/path/90254
        """
        range_header = f"bytes={start_byte}-{end_byte}" if end_byte is not None else f"bytes={start_byte}-"
        return self._make_stream_request(
            method="GET",
            endpoint="/media/get",
            chunk_size=chunk_size,
            range_header=range_header,
            params={"media_id": media_id},
        )
