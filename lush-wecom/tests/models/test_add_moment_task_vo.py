from __future__ import annotations

import pytest

from lush_wecom.models.add_moment_task_vo import (
    MAX_IMAGE_COUNT,
    MAX_LINK_TITLE_BYTES,
    MAX_LINK_TITLE_LENGTH,
    MAX_LINK_URL_BYTES,
    MAX_TEXT_BYTES,
    MAX_TEXT_LENGTH,
    AddMomentAttachment,
    AddMomentImageAttachment,
    AddMomentLinkAttachment,
    AddMomentTaskRequest,
    AddMomentText,
    AddMomentVideoAttachment,
    validate_moment_attachments_count,
    validate_moment_attachments_mixed_type,
    validate_moment_content,
    validate_moment_link_title,
    validate_moment_link_url,
    validate_moment_text_content,
)


def test_validate_moment_text_content_errors_and_success() -> None:
    with pytest.raises(ValueError, match="不能为空"):
        validate_moment_text_content("")

    with pytest.raises(ValueError, match=str(MAX_TEXT_LENGTH)):
        validate_moment_text_content("a" * (MAX_TEXT_LENGTH + 1))

    # Bytes overflow with multi-byte chars but within char length limit.
    too_many_bytes = "汉" * (MAX_TEXT_BYTES // 2)  # 2 bytes? actual is 3 bytes, but enough to overflow
    while len(too_many_bytes.encode("utf-8")) <= MAX_TEXT_BYTES:
        too_many_bytes += "汉"
    with pytest.raises(ValueError, match=str(MAX_TEXT_BYTES)):
        validate_moment_text_content(too_many_bytes)

    assert validate_moment_text_content("ok") == "ok"


def test_validate_moment_attachments_count_branches() -> None:
    validate_moment_attachments_count("image", MAX_IMAGE_COUNT)
    with pytest.raises(ValueError):
        validate_moment_attachments_count("image", MAX_IMAGE_COUNT + 1)

    with pytest.raises(ValueError, match="unknown"):
        validate_moment_attachments_count("unknown", 1)  # type: ignore[arg-type]


def test_validate_moment_attachments_mixed_type_branches() -> None:
    validate_moment_attachments_mixed_type([])

    a1 = AddMomentAttachment(msgtype="image", image=AddMomentImageAttachment(media_id="m"))
    a2 = AddMomentAttachment(msgtype="image", image=AddMomentImageAttachment(media_id="m2"))
    validate_moment_attachments_mixed_type([a1, a2])

    b1 = AddMomentAttachment(msgtype="video", video=AddMomentVideoAttachment(media_id="v"))
    with pytest.raises(ValueError, match="不能混合"):
        validate_moment_attachments_mixed_type([a1, b1])


def test_validate_moment_link_title_and_url() -> None:
    with pytest.raises(ValueError, match="不能为空"):
        validate_moment_link_title("")
    with pytest.raises(ValueError, match=str(MAX_LINK_TITLE_LENGTH)):
        validate_moment_link_title("a" * (MAX_LINK_TITLE_LENGTH + 1))

    # bytes overflow
    title = "汉"
    while len(title.encode("utf-8")) <= MAX_LINK_TITLE_BYTES:
        title += "汉"
    with pytest.raises(ValueError, match=str(MAX_LINK_TITLE_BYTES)):
        validate_moment_link_title(title)

    assert validate_moment_link_title("ok") == "ok"

    with pytest.raises(ValueError, match="不能为空"):
        validate_moment_link_url("")

    url = "a"
    while len(url.encode("utf-8")) <= MAX_LINK_URL_BYTES:
        url += "a"
    with pytest.raises(ValueError, match=str(MAX_LINK_URL_BYTES)):
        validate_moment_link_url(url)

    assert validate_moment_link_url("https://example.com") == "https://example.com"


def test_validate_moment_content_branches() -> None:
    with pytest.raises(ValueError, match="不能为空"):
        validate_moment_content(None, None)

    validate_moment_content(AddMomentText(content="hi"), None)

    img = AddMomentAttachment(msgtype="image", image=AddMomentImageAttachment(media_id="m"))
    validate_moment_content(None, [img])

    # Mixed types
    vid = AddMomentAttachment(msgtype="video", video=AddMomentVideoAttachment(media_id="v"))
    with pytest.raises(ValueError, match="不能混合"):
        validate_moment_content(None, [img, vid])

    # Too many images
    imgs = [AddMomentAttachment(msgtype="image", image=AddMomentImageAttachment(media_id=str(i))) for i in range(MAX_IMAGE_COUNT + 1)]
    with pytest.raises(ValueError):
        validate_moment_content(None, imgs)


def test_models_validate_attachment_and_request() -> None:
    # Attachment validator: missing field
    with pytest.raises(ValueError, match="必须提供"):
        _ = AddMomentAttachment(msgtype="image")

    # Link attachment validators
    link = AddMomentLinkAttachment(title="t", url="https://example.com", media_id="m")
    att = AddMomentAttachment(msgtype="link", link=link)
    assert att.link is not None

    # Request validator
    req = AddMomentTaskRequest(text=AddMomentText(content="hi"), attachments=None, visible_range=None)
    assert req.text is not None

    with pytest.raises(ValueError, match="发送内容不能为空"):
        _ = AddMomentTaskRequest(text=None, attachments=None, visible_range=None)
