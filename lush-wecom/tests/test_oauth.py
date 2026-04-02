from __future__ import annotations

from lush_wecom.utils.oauth import build_oauth_authorize_url


def test_build_oauth_authorize_url_minimal() -> None:
    url = build_oauth_authorize_url(
        corpid="ww123",
        redirect_uri="https://example.com/callback?x=1",
    )
    assert url.startswith("https://open.weixin.qq.com/connect/oauth2/authorize?")
    assert "appid=ww123" in url
    assert "redirect_uri=https%3A%2F%2Fexample.com%2Fcallback%3Fx%3D1" in url
    assert "response_type=code" in url
    assert "scope=snsapi_base" in url
    assert "#wechat_redirect" in url
    assert "state=" not in url
    assert "agentid=" not in url


def test_build_oauth_authorize_url_with_state_and_agentid() -> None:
    url = build_oauth_authorize_url(
        corpid="ww123",
        redirect_uri="https://example.com/callback",
        scope="snsapi_privateinfo",
        state="demo",
        agentid=100,
    )
    assert "scope=snsapi_privateinfo" in url
    assert "state=demo" in url
    assert "agentid=100" in url
