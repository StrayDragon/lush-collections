from __future__ import annotations

import pytest

from lush_wecom.utils.media_validators import (
    ImageResolutionError,
    _validate_moment_image_dimensions,
    ensure_attachment_upload_constraints,
)


def test_attachment_upload_accepts_valid_moment_image() -> None:
    assert ensure_attachment_upload_constraints("image", 1, 1024) == "image"


def test_attachment_upload_rejects_invalid_album_video() -> None:
    with pytest.raises(ValueError):
        ensure_attachment_upload_constraints("video", 2, 1024)


def test_attachment_upload_rejects_oversized_file() -> None:
    with pytest.raises(ValueError):
        ensure_attachment_upload_constraints("file", 1, 11 * 1024 * 1024)

    with pytest.raises(ValueError, match="不能超过"):
        ensure_attachment_upload_constraints("image", 1, 11 * 1024 * 1024)


def test_attachment_upload_normalizes_media_type() -> None:
    assert ensure_attachment_upload_constraints(" Video ", 1, 1024) == "video"


def test_attachment_upload_rejects_invalid_media_type() -> None:
    with pytest.raises(ValueError, match="media_type"):
        ensure_attachment_upload_constraints("unknown", 1, 1024)


def test_attachment_upload_rejects_invalid_attachment_type() -> None:
    with pytest.raises(ValueError, match="attachment_type"):
        ensure_attachment_upload_constraints("image", 999, 1024)  # type: ignore[arg-type]


def test_attachment_upload_rejects_small_file() -> None:
    with pytest.raises(ValueError, match="必须大于 5"):
        ensure_attachment_upload_constraints("image", 1, 5)


def test_validate_moment_image_dimensions_branches() -> None:
    with pytest.raises(ImageResolutionError, match="长边不能超过"):
        _validate_moment_image_dimensions(20000, 1)

    with pytest.raises(ImageResolutionError, match="短边不能超过"):
        _validate_moment_image_dimensions(2000, 2000)

    with pytest.raises(ImageResolutionError, match="最小需要"):
        _validate_moment_image_dimensions(0, 10)

    assert _validate_moment_image_dimensions(10, 20) == (10, 20)
