"""安全相关异常定义."""


class SecurityException(Exception):  # noqa: N818
    """安全模块基础异常."""


class EncryptionException(SecurityException):
    """加密处理异常."""


class DecryptionException(SecurityException):
    """解密处理异常."""


class TokenExpiredException(SecurityException):
    """令牌已过期."""


class TokenInvalidException(SecurityException):
    """令牌无效."""


class TokenFormatException(SecurityException):
    """令牌格式错误."""


__all__ = [
    "DecryptionException",
    "EncryptionException",
    "SecurityException",
    "TokenExpiredException",
    "TokenFormatException",
    "TokenInvalidException",
]
