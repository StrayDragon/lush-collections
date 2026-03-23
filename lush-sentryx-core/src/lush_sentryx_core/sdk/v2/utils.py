"""Sentryx Core SDK v2 工具函数

包含数据序列化、脱敏处理等辅助函数.
此模块不依赖 sentry-sdk, 可被任何 Sentry SDK 版本使用.
"""

from typing import Any

from lush_sentryx_core.sdk.v2.const import SENSITIVE_URL_PATTERNS
from lush_sentryx_core.sdk.v2.types import Request, User


def custom_repr(value: Any) -> str | None:
    """创建自定义变量序列化函数,保持基本类型的清晰展示

    Sentry SDK 默认使用 repr() 序列化局部变量,这会导致:
    - 字符串 "hello" → "'hello'" (多了引号)
    - 布尔值 False → "'False'" (变成字符串)
    - 数字 123 → "'123'" (变成字符串)

    此函数提供自定义序列化逻辑,对基本 JSON 可序列化类型保持清晰的原始格式,
    同时让复杂对象继续使用默认的 repr() 表示.

    Args:
        value: 需要序列化的任意值

    Returns:
        str | None: 序列化后的字符串,或 None (让调用者使用默认处理)

    Note:
        此函数用于 sentry_sdk.init() 的 custom_repr 参数 (SDK 2.12.0+)

    Example:
        >>> custom_repr(True)
        'True'
        >>> custom_repr(123)
        '123'
        >>> custom_repr("hello")
        'hello'
        >>> custom_repr(None)
        'None'
        >>> custom_repr([1, 2])
        None
    """
    if isinstance(value, (dict, list, tuple, set)):
        return None

    # 注意: bool 必须在 int 之前检查,因为 bool 是 int 的子类
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    if value is None:
        return "None"

    return None


def mask_email_partially(email: str) -> str:
    """对邮箱进行部分脱敏,保留识别性

    将 user@example.com 转换为 use***@example.com,
    在保护隐私的同时保留一定的识别能力.

    Args:
        email: 邮箱地址字符串

    Returns:
        脱敏后的邮箱地址

    Example:
        >>> mask_email_partially("user@example.com")
        'use***@example.com'
        >>> mask_email_partially("ab@example.com")
        '***@example.com'
        >>> mask_email_partially("invalid-email")
        'invalid-email'
    """
    if "@" not in email:
        return email

    username, domain = email.split("@", 1)
    if len(username) > 3:
        return username[:3] + "***@" + domain
    return "***@" + domain


def mask_user_email_partially(user: User | dict[str, Any]) -> None:
    """对用户字典中的邮箱进行部分脱敏,保留识别性

    将 user@example.com 转换为 use***@example.com,
    在保护隐私的同时保留一定的识别能力.

    Args:
        user: 用户数据字典 (符合 Sentry User 结构),可能包含 'email' 或 'mail' 字段

    Note:
        - 此函数会原地修改传入的 user 字典
        - 如果邮箱格式无效或为空,保持不变
        - 支持 'email' 和 'mail' 两种字段名

    Example:
        >>> user = {"email": "user@example.com", "id": "123"}
        >>> mask_user_email_partially(user)
        >>> user["email"]
        'use***@example.com'
    """
    for field_name in ["email", "mail"]:
        if field_name not in user:
            continue

        value = user[field_name]  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(value, str) or "@" not in value:
            continue

        user[field_name] = mask_email_partially(value)


def parameterize_request_urls(request: Request | dict[str, Any]) -> None:
    """清理请求 URL 中的敏感查询参数

    将 /api/endpoint?token=secret123 转换为 /api/endpoint (移除查询参数),
    防止敏感信息泄露到事件中.

    Args:
        request: 请求数据字典 (符合 Sentry Request 结构)

    Note:
        - 此函数会原地修改传入的 request 字典
        - 只有当 URL 包含敏感查询参数时才会修改
        - 会同时移除 url 中的查询字符串和 query_string 字段

    Example:
        >>> request = {"url": "https://api.example.com/users?token=secret123", "query_string": "token=secret123"}
        >>> parameterize_request_urls(request)
        >>> request["url"]
        'https://api.example.com/users'
        >>> "query_string" in request
        False
    """
    url = request.get("url", "")
    if not isinstance(url, str):
        return

    for pattern in SENSITIVE_URL_PATTERNS:
        if pattern.search(url):
            _ = request.pop("query_string", None)
            if "?" in url:
                url = url.split("?")[0]
                request["url"] = url
            break


def mask_string_partially(
    value: str,
    visible_prefix: int = 3,
    visible_suffix: int = 0,
    mask_char: str = "*",
    min_mask_length: int = 3,
) -> str:
    """对字符串进行部分脱敏

    Args:
        value: 要脱敏的字符串
        visible_prefix: 保留前缀的字符数
        visible_suffix: 保留后缀的字符数
        mask_char: 脱敏字符
        min_mask_length: 最小脱敏字符数

    Returns:
        脱敏后的字符串

    Example:
        >>> mask_string_partially("1234567890", visible_prefix=3, visible_suffix=2)
        '123*****90'
        >>> mask_string_partially("abc", visible_prefix=3)
        '***'
    """
    if len(value) <= visible_prefix + visible_suffix:
        return mask_char * min_mask_length

    masked_length = max(len(value) - visible_prefix - visible_suffix, min_mask_length)
    prefix = value[:visible_prefix] if visible_prefix > 0 else ""
    suffix = value[-visible_suffix:] if visible_suffix > 0 else ""
    return prefix + (mask_char * masked_length) + suffix
