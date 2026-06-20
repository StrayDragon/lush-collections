"""Sentryx Core SDK v2 常量定义

包含敏感数据字段列表、URL 模式等常量.
此模块不依赖 sentry-sdk, 可被任何 Sentry SDK 版本使用.
"""

import re
from re import Pattern
from typing import Final

# Sentry SDK 2.x 默认的敏感字段列表
# 参考: https://github.com/getsentry/sentry-python/blob/master/sentry_sdk/scrubber.py
#
# 这些字段在 EventScrubber 中使用子串匹配 (不区分大小写)
# 例如: 'token' 会匹配 'access_token', 'user_token', 'my_token_field' 等
SENTRY_DEFAULT_DENYLIST: Final[frozenset[str]] = frozenset(
    {
        # 认证相关
        "password",
        "passwd",
        "secret",
        "api_key",
        "apikey",
        "access_token",
        "auth",
        "credentials",
        "token",
        "api_secret",
        "app_secret",
        "client_secret",
        "private_key",
        "public_key",
        "signing_key",
        "encryption_key",
        "session_key",
        "session_id",
        "sessionid",
        # HTTP Headers
        "authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "x-auth-token",
        "x-csrf-token",
        "x-forwarded-for",
        "x-real-ip",
        # 个人身份信息
        "email",
        "phone",
        "ssn",
        "social_security",
        "credit_card",
        "card_number",
        "cvv",
        "pin",
        # 数据库连接
        "mysql_pwd",
        "postgres_password",
        "db_password",
        "database_url",
        "connection_string",
        # 其他敏感信息
        "jwt",
        "bearer",
        "oauth",
        "refresh_token",
        "id_token",
    }
)


# URL中可能包含敏感信息的模式
SENSITIVE_URL_PATTERNS: Final[list[Pattern[str]]] = [
    re.compile(r"[\?&](?:token|key|secret|password|api_key)=[\w\-\.]+", re.IGNORECASE),
]

# 默认的过滤替换值
FILTERED_PLACEHOLDER: Final[str] = "[Filtered]"
