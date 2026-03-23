"""Sentryx Core SDK v2 数据清理器

提供敏感数据清理功能,确保事件不包含敏感信息.
此模块不依赖 sentry-sdk, 可被任何 Sentry SDK 版本使用.
"""

import contextlib
from typing import Any

from lush_sentryx_core.sdk.v2.const import FILTERED_PLACEHOLDER
from lush_sentryx_core.sdk.v2.types import Event, SensitiveFields


def deep_scrub_sensitive_data(
    data: Any,
    sensitive_fields: SensitiveFields,
    max_depth: int = 10,
    _current_depth: int = 0,
    placeholder: str = FILTERED_PLACEHOLDER,
) -> None:
    """深度递归清理敏感数据

    此函数用于递归遍历数据结构,将包含敏感字段名的值替换为占位符.
    适用于任何需要清理敏感数据的场景,不限于 Sentry.

    Args:
        data: 要清理的数据(字典、列表或其他类型)
        sensitive_fields: 敏感字段名的集合
        max_depth: 最大递归深度,防止无限递归 (默认 10 层)
        _current_depth: 当前递归深度(内部使用,不应手动设置)
        placeholder: 替换敏感数据的占位符

    Note:
        - 仅处理 dict 和 list/tuple 类型,其他类型保持不变
        - 使用子串不区分大小写匹配检查字段名
        - 性能考虑: 限制最大递归深度避免栈溢出
        - 会原地修改传入的数据结构

    Example:
        >>> data = {"config": {"corpid": "ww123", "access_token": "secret", "normal": "value"}}
        >>> fields = {"corpid", "access_token", "password"}
        >>> deep_scrub_sensitive_data(data, fields)
        >>> data
        {'config': {'corpid': '[Filtered]', 'access_token': '[Filtered]', 'normal': 'value'}}
    """
    if _current_depth >= max_depth:
        return

    if isinstance(data, dict):
        keys_to_scrub: list[str] = []
        for key in list(data.keys()):  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
            key_str = str(key).lower()  # pyright: ignore[reportUnknownArgumentType]
            is_sensitive = any(deny.lower() in key_str or key_str in deny.lower() for deny in sensitive_fields)

            if is_sensitive:
                keys_to_scrub.append(key)  # pyright: ignore[reportUnknownArgumentType]
            else:
                deep_scrub_sensitive_data(data[key], sensitive_fields, max_depth, _current_depth + 1, placeholder)

        for key in keys_to_scrub:
            data[key] = placeholder

    elif isinstance(data, (list, tuple)):
        for item in data:  # pyright: ignore[reportUnknownVariableType]
            deep_scrub_sensitive_data(item, sensitive_fields, max_depth, _current_depth + 1, placeholder)


def scrub_stacktrace_vars(
    event: Event,
    sensitive_fields: SensitiveFields,
    placeholder: str = FILTERED_PLACEHOLDER,
) -> None:
    """清理堆栈帧中局部变量的嵌套敏感数据

    此函数遍历 Sentry 事件中的所有堆栈帧,对每个局部变量进行深度清理.
    适用于 Sentry SDK 2.x 的事件结构.

    Args:
        event: Sentry 事件对象 (符合 SDK 2.x 结构)
        sensitive_fields: 敏感字段名的集合
        placeholder: 替换敏感数据的占位符

    Note:
        - 处理 exception 和 threads 中的 stacktrace
        - 原地修改局部变量的值
        - 保留变量结构,只过滤敏感字段

    Example:
        局部变量 wecom_config = {'corpid': 'ww123', 'name': 'test'}
        会被处理为: {'corpid': '[Filtered]', 'name': 'test'}
    """
    with contextlib.suppress(Exception):  # 静默处理异常,避免影响主流程
        # 处理异常堆栈帧中的局部变量
        if "exception" in event:
            exception_data = event["exception"]
            values = exception_data.get("values", [])
            for exception_value in values:
                stacktrace = exception_value.get("stacktrace", {})
                frames = stacktrace.get("frames", [])
                for frame in frames:
                    if "vars" in frame and isinstance(frame["vars"], dict):
                        for _var_name, var_value in list(frame["vars"].items()):
                            if isinstance(var_value, (dict, list)):
                                deep_scrub_sensitive_data(var_value, sensitive_fields, placeholder=placeholder)

        # 处理线程堆栈 (如果有)
        if "threads" in event:
            threads_data = event["threads"]
            values = threads_data.get("values", [])
            for thread_value in values:
                stacktrace = thread_value.get("stacktrace", {})
                frames = stacktrace.get("frames", [])
                for frame in frames:
                    if "vars" in frame and isinstance(frame["vars"], dict):
                        for _var_name, var_value in list(frame["vars"].items()):
                            if isinstance(var_value, (dict, list)):
                                deep_scrub_sensitive_data(var_value, sensitive_fields, placeholder=placeholder)


def scrub_dict_keys(
    data: dict[str, Any],
    sensitive_fields: SensitiveFields,
    placeholder: str = FILTERED_PLACEHOLDER,
) -> dict[str, Any]:
    """清理字典中的敏感字段 (非递归,仅顶层)

    Args:
        data: 要清理的字典
        sensitive_fields: 敏感字段名的集合
        placeholder: 替换敏感数据的占位符

    Returns:
        清理后的字典副本

    Example:
        >>> data = {"password": "secret", "username": "john"}
        >>> scrub_dict_keys(data, {"password"})
        {'password': '[Filtered]', 'username': 'john'}
    """
    result = dict(data)
    for key in result:
        key_str = str(key).lower()
        if any(deny.lower() in key_str or key_str in deny.lower() for deny in sensitive_fields):
            result[key] = placeholder
    return result
