"""Sentryx 数据清理器

提供敏感数据清理功能,确保 Sentry 事件不包含敏感信息.
核心清理逻辑来自 lush_sentryx_core.sdk.v2,此模块提供 Sentry SDK 2.x 特定的封装.
"""

import logging

from lush_sentryx_core.sdk.v2 import (
    BUSINESS_SENSITIVE_FIELDS,
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
    enable_business_fields: bool = True,
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
        denylist: 额外的敏感字段列表,会与默认字段合并
        enable_business_fields: 是否启用业务敏感字段过滤 (默认 True)

    Returns:
        EventScrubber: 配置了业务特定敏感字段的清理器

    Note:
        - Sentry 默认的 DEFAULT_DENYLIST 始终启用
        - 业务敏感字段 (BUSINESS_SENSITIVE_FIELDS) 根据 enable_business_fields 参数控制

    Example:
        >>> scrubber = create_enhanced_scrubber(denylist={"custom_secret", "internal_token"}, enable_business_fields=True)

    See Also:
        - https://docs.sentry.io/platforms/python/data-management/sensitive-data/
    """
    try:
        # 始终包含 Sentry 默认敏感字段
        final_denylist: set[str] = set(SENTRY_DEFAULT_DENYLIST)

        # 根据参数决定是否添加业务敏感字段
        if enable_business_fields:
            final_denylist |= set(BUSINESS_SENSITIVE_FIELDS)
        else:
            _logger.warning("⚠️ 业务敏感字段过滤已禁用 - 仅使用 Sentry 默认过滤")

        # 添加用户自定义字段
        if denylist:
            final_denylist |= denylist

        # EventScrubber 在 SDK 2.x 中只接受 denylist 参数
        # send_default_pii 应该在 sentry_sdk.init() 中设置
        return EventScrubber(denylist=list(final_denylist))
    except Exception as e:
        _logger.warning("创建EventScrubber失败, 使用默认配置: %s", e)
        # 降级方案: 使用默认配置
        return EventScrubber()


def get_all_sensitive_fields(
    enable_business_fields: bool = True,
    additional_denylist: set[str] | None = None,
) -> set[str]:
    """获取所有敏感字段的集合

    Args:
        enable_business_fields: 是否包含业务敏感字段
        additional_denylist: 额外的敏感字段

    Returns:
        所有敏感字段的集合
    """
    result = set(SENTRY_DEFAULT_DENYLIST)
    if enable_business_fields:
        result |= set(BUSINESS_SENSITIVE_FIELDS)
    if additional_denylist:
        result |= additional_denylist
    return result
