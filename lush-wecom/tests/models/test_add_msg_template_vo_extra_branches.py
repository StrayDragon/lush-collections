from __future__ import annotations

import pytest

from lush_wecom.models.add_msg_template_vo import (
    MAX_LINK_DESC_BYTES,
    MAX_LINK_PICURL_BYTES,
    validate_link_desc,
    validate_link_picurl,
    validate_link_title,
    validate_link_url,
    validate_miniprogram_title,
)


def test_add_msg_template_validation_error_branches() -> None:
    with pytest.raises(ValueError, match="链接标题不能为空"):
        validate_link_title("")
    with pytest.raises(ValueError, match="链接URL不能为空"):
        validate_link_url("")
    with pytest.raises(ValueError, match="小程序标题不能为空"):
        validate_miniprogram_title("")

    assert validate_link_desc(None) is None
    assert validate_link_picurl(None) is None

    assert validate_link_desc("ok") == "ok"
    assert validate_link_picurl("https://example.com/x.png") == "https://example.com/x.png"

    desc = "a"
    while len(desc.encode("utf-8")) <= MAX_LINK_DESC_BYTES:
        desc += "a"
    with pytest.raises(ValueError, match=str(MAX_LINK_DESC_BYTES)):
        validate_link_desc(desc)

    picurl = "a"
    while len(picurl.encode("utf-8")) <= MAX_LINK_PICURL_BYTES:
        picurl += "a"
    with pytest.raises(ValueError, match=str(MAX_LINK_PICURL_BYTES)):
        validate_link_picurl(picurl)
