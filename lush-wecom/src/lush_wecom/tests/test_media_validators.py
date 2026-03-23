import pytest

from lush_wecom.utils.media_validators import ensure_attachment_upload_constraints


def test_attachment_upload_accepts_valid_moment_image() -> None:
    assert ensure_attachment_upload_constraints("image", 1, 1024) == "image"


def test_attachment_upload_rejects_invalid_album_video() -> None:
    with pytest.raises(ValueError):
        ensure_attachment_upload_constraints("video", 2, 1024)


def test_attachment_upload_rejects_oversized_file() -> None:
    with pytest.raises(ValueError):
        ensure_attachment_upload_constraints("file", 1, 11 * 1024 * 1024)


def test_attachment_upload_normalizes_media_type() -> None:
    assert ensure_attachment_upload_constraints(" Video ", 1, 1024) == "video"
