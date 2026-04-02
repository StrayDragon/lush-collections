from __future__ import annotations

from lush_wecom.models.send_app_message_vo import SendAppMessageResponse


def test_send_app_message_response_failure_reason() -> None:
    assert SendAppMessageResponse(errcode=0, errmsg="ok").get_failure_reason_when_send_only_one_user() == ""

    resp1 = SendAppMessageResponse(errcode=0, errmsg="ok", invaliduser="BADUSER")
    assert "不合法的userid" in resp1.get_failure_reason_when_send_only_one_user()

    resp2 = SendAppMessageResponse(errcode=0, errmsg="ok", unlicenseduser="NO-LIC")
    assert "没有基础接口许可" in resp2.get_failure_reason_when_send_only_one_user()
