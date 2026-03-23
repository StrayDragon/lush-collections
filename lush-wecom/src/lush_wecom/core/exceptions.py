import httpx


class WeComError(Exception):
    """SDK的基础异常类"""


class WeComHTTPError(WeComError):
    """当HTTP请求失败时抛出"""

    def __init__(self, message: str, original_exception: httpx.HTTPStatusError) -> None:
        self.original_exception: httpx.HTTPStatusError = original_exception
        super().__init__(f"{message}: {original_exception}")


class WeComAPIError(WeComError):
    """当企业微信API返回错误码时抛出"""

    def __init__(self, message: str = "", errcode: int | None = None, errmsg: str = "") -> None:
        self.errcode: int | None = errcode
        self.errmsg: str = errmsg
        self.message: str = message or errmsg
        if errcode is not None:
            super().__init__(f"errcode: {errcode}, errmsg: {errmsg}")
        else:
            super().__init__(self.message)


class WeComResponseValidationError(WeComError):
    """当API响应无法通过Pydantic模型验证时抛出"""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class InvalidTokenError(WeComAPIError):
    """当access_token无效时抛出"""
