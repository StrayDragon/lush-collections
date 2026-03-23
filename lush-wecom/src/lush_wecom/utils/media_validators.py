"""
媒体上传相关校验工具
"""

from __future__ import annotations

import io
from pathlib import Path

from lush_wecom.core.const import (
    ATTACHMENT_FILE_SIZE_LIMITS,
    ATTACHMENT_TYPE_MEDIA_LIMITS,
    MOMENT_IMAGE_MAX_LONG_EDGE,
    MOMENT_IMAGE_MAX_SHORT_EDGE,
    MOMENT_IMAGE_MIN_DIMENSION,
    AttachmentTypeLiteral,
)


def ensure_attachment_upload_constraints(
    media_type: str,
    attachment_type: AttachmentTypeLiteral,
    file_size: int,
) -> str:
    """
    校验附件上传的媒体类型、附件类型以及文件大小限制

    Args:
        media_type: 媒体类型,仅支持 image/video/file
        attachment_type: 附件类型,1表示朋友圈,2表示商品图册
        file_size: 文件大小(字节)

    Returns:
        str: 按API要求格式化(小写)后的 media_type
    """
    normalized_media_type = media_type.strip().lower()

    if normalized_media_type not in ATTACHMENT_FILE_SIZE_LIMITS:
        valid_types = ", ".join(ATTACHMENT_FILE_SIZE_LIMITS)
        raise ValueError(f"media_type 必须是 {valid_types} 之一, 当前: {media_type}")

    if attachment_type not in ATTACHMENT_TYPE_MEDIA_LIMITS:
        valid_attachment_types = ", ".join(str(key) for key in ATTACHMENT_TYPE_MEDIA_LIMITS)
        raise ValueError(f"attachment_type 必须是 {valid_attachment_types} 之一, 当前: {attachment_type}")

    allowed_media_types = ATTACHMENT_TYPE_MEDIA_LIMITS[attachment_type]
    if normalized_media_type not in allowed_media_types:
        readable_allowed = ", ".join(allowed_media_types)
        raise ValueError(
            f"附件类型 {attachment_type} 仅支持媒体类型 {readable_allowed}, 当前: {normalized_media_type}",
        )

    if file_size <= 5:
        raise ValueError("文件大小必须大于 5 个字节")

    max_size = ATTACHMENT_FILE_SIZE_LIMITS[normalized_media_type]
    if file_size > max_size:
        max_size_mb = max_size // (1024 * 1024)
        raise ValueError(f"{normalized_media_type} 文件大小不能超过 {max_size_mb}MB")

    return normalized_media_type


class ImageResolutionError(ValueError):
    """图片分辨率不符合要求"""

    def __init__(self, message: str, width: int, height: int) -> None:
        super().__init__(message)
        self.width = width
        self.height = height


def _validate_moment_image_dimensions(width: int, height: int) -> tuple[int, int]:
    """内部校验函数,检查图片尺寸是否符合朋友圈要求"""
    long_edge = max(width, height)
    short_edge = min(width, height)

    if long_edge > MOMENT_IMAGE_MAX_LONG_EDGE:
        raise ImageResolutionError(
            f"朋友圈图片长边不能超过 {MOMENT_IMAGE_MAX_LONG_EDGE} 像素, 当前: {long_edge}px",
            width,
            height,
        )

    if short_edge > MOMENT_IMAGE_MAX_SHORT_EDGE:
        raise ImageResolutionError(
            f"朋友圈图片短边不能超过 {MOMENT_IMAGE_MAX_SHORT_EDGE} 像素, 当前: {short_edge}px",
            width,
            height,
        )

    if width < MOMENT_IMAGE_MIN_DIMENSION or height < MOMENT_IMAGE_MIN_DIMENSION:
        raise ImageResolutionError(
            f"图片尺寸过小, 最小需要 {MOMENT_IMAGE_MIN_DIMENSION}x{MOMENT_IMAGE_MIN_DIMENSION} 像素",
            width,
            height,
        )

    return width, height


def check_moment_image_resolution(file_path: str | Path) -> tuple[int, int]:
    """
    检查朋友圈图片的分辨率是否符合企微要求

    企微朋友圈图片要求:
    - 长边不超过 10800 像素
    - 短边不超过 1080 像素

    Args:
        file_path: 图片文件路径

    Returns:
        tuple[int, int]: (width, height) 图片尺寸

    Raises:
        ImageResolutionError: 分辨率不符合要求
        ValueError: 无法读取图片
    """
    try:
        from PIL import Image  # noqa: PLC0415
    except ImportError as e:
        raise ImportError("需要安装 Pillow 库: pip install Pillow") from e

    path = Path(file_path)
    if not path.exists():
        raise ValueError(f"图片文件不存在: {file_path}")

    try:
        with Image.open(path) as img:
            width: int = img.size[0]
            height: int = img.size[1]
    except Exception as e:
        raise ValueError(f"无法读取图片: {e}") from e

    return _validate_moment_image_dimensions(width, height)


def check_moment_image_resolution_from_bytes(data: bytes) -> tuple[int, int]:
    """
    从图片字节数据检查朋友圈图片的分辨率是否符合企微要求

    Args:
        data: 图片字节数据

    Returns:
        tuple[int, int]: (width, height) 图片尺寸

    Raises:
        ImageResolutionError: 分辨率不符合要求
        ValueError: 无法读取图片
    """
    try:
        from PIL import Image  # noqa: PLC0415
    except ImportError as e:
        raise ImportError("需要安装 Pillow 库: pip install Pillow") from e

    try:
        with Image.open(io.BytesIO(data)) as img:
            width: int = img.size[0]
            height: int = img.size[1]
    except Exception as e:
        raise ValueError(f"无法读取图片: {e}") from e

    return _validate_moment_image_dimensions(width, height)


async def check_moment_image_resolution_from_url(url: str, timeout: float = 30.0) -> tuple[int, int]:
    """
    从图片 URL 下载并检查朋友圈图片的分辨率是否符合企微要求

    Args:
        url: 图片 URL
        timeout: 下载超时时间(秒)

    Returns:
        tuple[int, int]: (width, height) 图片尺寸

    Raises:
        ImageResolutionError: 分辨率不符合要求
        ValueError: 无法下载或读取图片
    """
    try:
        import httpx  # noqa: PLC0415
    except ImportError as e:
        raise ImportError("需要安装 httpx 库: pip install httpx") from e

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            _ = response.raise_for_status()
            data = response.content
    except Exception as e:
        raise ValueError(f"无法下载图片: {url}, 错误: {e}") from e

    return check_moment_image_resolution_from_bytes(data)
