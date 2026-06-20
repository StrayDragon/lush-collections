"""Sentryx 数据清理器

提供敏感数据清理功能,确保 Sentry 事件不包含敏感信息.
核心清理逻辑来自 lush_sentryx_core.sdk.v2,此模块提供 Sentry SDK 2.x 特定的封装.
"""

import logging

from lush_sentryx_core.sdk.v2 import (
    SENTRY_DEFAULT_DENYLIST,
    deep_scrub_sensitive_data,
    scrub_stacktrace_vars,
)
from sentry_sdk.scrubber import EventScrubber

_logger = logging.getLogger(__name__)

# 重新导出核心函数,保持向后兼容
__all__ = [
    "create_enhanced_scrubber",
    "deep_scrub_sensitive_data",
    "get_all_sensitive_fields",
    "scrub_stacktrace_vars",
]


def create_enhanced_scrubber(
    denylist: set[str] | None = None,
) -> EventScrubber:
    """创建增强的敏感数据清理器 (Sentry SDK 2.x)

    EventScrubber 使用 **子串匹配** (.*xxx.*) 自动递归清理敏感字段:
    - 匹配规则: 字段名包含 denylist 中的任意关键词即被过滤 (不区分大小写)
    - 示例: 'token' 会匹配 'access_token', 'user_token_id', 'my_token' 等

    自动清理的数据范围:
    - 请求数据 (headers, cookies, form data, JSON body, 字典参数)
    - 用户数据
    - 面包屑数据
    - 堆栈局部变量
    - 嵌套字典和列表 (递归处理)

    Args:
        denylist: 额外的敏感字段列表,会与 Sentry 默认字段合并

    Returns:
        EventScrubber: 配置了敏感字段的清理器

    Note:
        - Sentry 默认的 DEFAULT_DENYLIST 始终启用
        - 额外的业务敏感字段通过 denylist 参数传入

    Example:
        >>> scrubber = create_enhanced_scrubber(denylist={"custom_secret", "internal_token"})

    See Also:
        - https://docs.sentry.io/platforms/python/data-management/sensitive-data/
    """
    try:
        final_denylist: set[str] = set(SENTRY_DEFAULT_DENYLIST)

        if denylist:
            final_denylist |= denylist

        return EventScrubber(denylist=list(final_denylist))
    except Exception as e:
        _logger.warning("创建EventScrubber失败, 使用默认配置: %s", e)
        return EventScrubber()


def get_all_sensitive_fields(
    additional_denylist: set[str] | None = None,
) -> set[str]:
    """获取所有敏感字段的集合

    Args:
        additional_denylist: 额外的敏感字段

    Returns:
        所有敏感字段的集合
    """
    result = set(SENTRY_DEFAULT_DENYLIST)
    if additional_denylist:
        result |= additional_denylist
    return result
