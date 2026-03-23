# lush-collections 仓库全面审查报告

> 审查日期：2026-03-23
> 覆盖范围：全部 10 个包（lush-stdx, lush-logx, lush-pydanticx, lush-sqlalchemyx, lush-redisx, lush-fastapix, lush-sentryx-core, lush-sentryx, lush-wecom, lush-exp）

---

## 目录

- [一、安全问题](#一安全问题)
- [二、代码质量](#二代码质量)
- [三、漏洞/Bug](#三漏洞bug)
- [四、竞态条件](#四竞态条件)
- [五、测试不稳定性](#五测试不稳定性)
- [六、代码可维护性与命令重复](#六代码可维护性与命令重复)
- [七、优先级总览与推荐解决方案](#七优先级总览与推荐解决方案)

---

## 一、安全问题

### SEC-01 [高] 企业微信 media_url 下载存在 SSRF 风险

**位置**：`lush-wecom/src/lush_wecom/client/_sync/__init__.py` (~687–738 行)，`_async/__init__.py` 对应段

**描述**：`upload_attachment_media_from_url` / `upload_temporary_media_from_url` 对传入的 `media_url` 直接执行 `httpx.head(...)` 与 `httpx.stream("GET", ...)`，未校验协议、主机、内网/元数据地址、重定向目标。攻击者可诱导服务器请求内网、云元数据端点或进行端口探测。

**推荐方案**：

```python
# 新增 URL 校验工具函数
import ipaddress
from urllib.parse import urlparse

_BLOCKED_HOSTS = {"169.254.169.254", "metadata.google.internal"}
_ALLOWED_SCHEMES = {"http", "https"}

def validate_external_url(url: str) -> None:
    """校验 URL 不指向内网或云元数据端点"""
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise ValueError(f"不允许的协议: {parsed.scheme}")
    hostname = parsed.hostname or ""
    if hostname in _BLOCKED_HOSTS:
        raise ValueError(f"不允许的主机: {hostname}")
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            raise ValueError(f"不允许的内网地址: {ip}")
    except ValueError:
        pass  # 域名非 IP，允许通过（可选加域名白名单）

# 在 _download_media_from_url 入口调用
def _download_media_from_url(self, media_url: str, ...):
    validate_external_url(media_url)
    # ... 原有逻辑
```

---

### SEC-02 [高] 加密 ID 可被明文查询参数绕过

**位置**：`lush-exp/src/lush_exp/lush_security/integrations/fastapi/depends/__init__.py` (49–50 行)

**描述**：`PageSecurityHelper.get_decrypted_id` 在尝试解密参数失败后，直接使用明文 `request.query_params.get(param_name)`。当 `enable_encryption=True` 时，攻击者仍可通过 `?id=123` 绕过加密令牌。

**推荐方案**：

```python
# 在 enable_encryption=True 时禁止明文回退
def get_decrypted_id(self, param_name: str = "id") -> int:
    # ... 尝试从 decrypted_params 获取 ...
    # ... 尝试从 *_encrypted 参数获取 ...

    if self._jwt_manager.config.enable_encryption:
        raise HTTPException(
            status_code=400,
            detail="加密参数缺失或无效",
        )

    # 仅在未启用加密时允许明文
    if normal_value := self.request.query_params.get(param_name):
        return int(normal_value)
    raise HTTPException(status_code=400, detail="参数缺失")
```

---

### SEC-03 [中] innodb_lock_wait_timeout 使用 f-string 拼接 SQL

**位置**：`lush-sqlalchemyx/src/lush_sqlalchemyx/base/dal/__init__.py` (116–119 行)

**描述**：`f"SET SESSION innodb_lock_wait_timeout = {timeout_seconds}"` 虽类型注解为 `int`，但缺乏运行时校验。

**推荐方案**：

```python
async def async_temp_set_lock_wait_timeout(session, timeout_seconds: int):
    if not isinstance(timeout_seconds, int) or not (1 <= timeout_seconds <= 3600):
        raise ValueError(f"timeout_seconds 必须为 1-3600 之间的整数，收到: {timeout_seconds}")
    await session.execute(
        sa.text("SET SESSION innodb_lock_wait_timeout = :timeout"),
        {"timeout": timeout_seconds},
    )
```

---

### SEC-04 [中] 限流/防抖在 Redis 异常时 fail-open

**位置**：`lush-redisx/src/lush_redisx/async_redis.py` (~272–332 行)

**描述**：Redis 出错时返回 `allowed=True`，限流失效。

**推荐方案**：

```python
@dataclass
class ThrottleConfig:
    fail_open: bool = True  # 默认保持向后兼容

async def throttle_check_and_set(self, key, ttl, *, fail_open: bool = True):
    try:
        # ... 原有逻辑
    except RedisError as e:
        logger.warning("Redis 限流异常: %s", e)
        if fail_open:
            return ThrottleResult(allowed=True, ...)
        raise ServiceUnavailableError("限流服务不可用") from e
```

---

### SEC-05 [中] 基于 X-Forwarded-For 的客户端 IP 信任

**位置**：`lush-redisx/src/lush_redisx/integrations/fastapi/depends/rate_limit.py` (87–91 行)

**描述**：客户端可伪造 `X-Forwarded-For` 头绕过限流。

**推荐方案**：

```python
class ClientIPRateLimitKeyBuilder:
    def __init__(self, trusted_proxy_depth: int = 1):
        """
        trusted_proxy_depth: 从 X-Forwarded-For 右侧取第 N 个 IP
        部署在单层代理后设为 1，两层设为 2
        """
        self._depth = trusted_proxy_depth

    def build_key(self, request: Request) -> str:
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            ips = [ip.strip() for ip in xff.split(",")]
            # 从右侧取可信代理注入的 IP
            idx = max(0, len(ips) - self._depth)
            client_ip = ips[idx]
        else:
            client_ip = request.client.host if request.client else "unknown"
        return f"rate_limit:{client_ip}"
```

---

### SEC-06 [中] 开发日志默认开启 Rich 局部变量

**位置**：`lush-logx/src/lush_logx/logging.py` (386–387 行)

**描述**：`RichHandler(tracebacks_show_locals=True)` 默认开启，异常栈可能打印 token、密码等。

**推荐方案**：

```python
@dataclass
class LogConfig:
    enable_rich: bool = True
    show_locals_in_tracebacks: bool = False  # 默认关闭，仅调试时手动开启

# 使用处
RichHandler(tracebacks_show_locals=config.show_locals_in_tracebacks)
```

---

### SEC-07 [中] CSP 默认包含 unsafe-inline

**位置**：`lush-exp/src/lush_exp/lush_security/csp.py` (27–29 行)

**描述**：非 strict 模式下 `script-src` 同时包含 nonce 与 `unsafe-inline`，削弱 XSS 防护。

**推荐方案**：默认改为 `strict=True`，或去除 `unsafe-inline`。

```python
class CSPManager:
    def __init__(self, strict: bool = True):  # 改默认值
        ...
```

---

### SEC-08 [中] JWTManager 关闭加密时无保护

**位置**：`lush-exp/src/lush_exp/lush_security/jwt_manager.py` (107–108 行)

**推荐方案**：在非 DEBUG 环境拒绝 `enable_encryption=False`。

```python
@dataclass
class JWTConfig:
    enable_encryption: bool = True

    def __post_init__(self):
        if not self.enable_encryption:
            import os
            if os.getenv("ENV", "production") != "development":
                raise ValueError("生产环境不允许关闭加密，设置 ENV=development 以覆盖")
```

---

### SEC-09 [低] 幂等守卫错误响应泄露 Redis 键名

**位置**：`lush-redisx/src/lush_redisx/integrations/fastapi/depends/idempotency.py` (158–164 行)

**推荐方案**：生产环境仅返回通用文案。

```python
def _default_exception_factory(redis_key: str, ttl_seconds: int):
    return HTTPException(
        status_code=409,
        detail="请求重复，请稍后重试",
    )
```

---

### SEC-10 [低] OpenAPI 增强器动态 __import__

**位置**：`lush-fastapix/src/lush_fastapix/schema_enhancer.py` (198–203 行)

**推荐方案**：对模块名做白名单校验。

```python
_ALLOWED_ENUM_MODULE_PREFIXES = ("lush_", "app.", "models.")

def _enhance_direct_enum_schema(schema, ...):
    enum_module = schema.get("x-enum-module", "")
    if not any(enum_module.startswith(p) for p in _ALLOWED_ENUM_MODULE_PREFIXES):
        return schema
    # ... 原有逻辑
```

---

### SEC-11 [低] Mock 模式返回固定假 token

**位置**：`lush-wecom/src/lush_wecom/core/token_mgr.py` (26–27 行)

**推荐方案**：启动时检测环境，非测试环境禁用 mock。

---

### SEC-12 [低] JWT 异常信息过细

**位置**：`lush-exp/src/lush_exp/lush_security/jwt_manager.py` (192 行)

**推荐方案**：对用户返回统一文案，详细原因仅写日志。

---

## 二、代码质量

### CQ-01 [Critical] Sentry additional_filter 在异常时静默丢弃事件

**位置**：`lush-sentryx-core/src/lush_sentryx_core/sdk/v2/filters.py` (50–78 行)

**描述**：`additional_filter` 内层用 `except Exception` 包全部逻辑，异常时返回 `None`，导致整类事件被丢弃。

**推荐方案**：

```python
def additional_filter(event, hint):
    try:
        # ... 过滤逻辑
    except Exception:
        logger.warning("Sentry 过滤器异常，返回原始事件", exc_info=True)
        return event  # 异常时保留事件，而非丢弃
```

---

### CQ-02 [Critical] LogConfig.level 未执行 .upper()

**位置**：`lush-logx/src/lush_logx/logging.py` (94–96 行)

**描述**：注释写"规范化日志级别为大写"，但 `self.level = self.level` 为无操作。

**推荐方案**：

```python
def __post_init__(self):
    self.level = self.level.upper()  # 修复：实际执行大写转换
    self.min_json_level = self.min_json_level.upper()
    # ...
```

---

### CQ-03 [高] dal/__init__.py 超过 2000 行（God Module）

**位置**：`lush-sqlalchemyx/src/lush_sqlalchemyx/base/dal/__init__.py`

**推荐方案**：按职责拆分为子模块。

```
lush_sqlalchemyx/base/dal/
├── __init__.py          # 仅做 re-export
├── retry.py             # async_with_retry 等重试逻辑
├── soft_delete.py       # 软删除 mixin 与过滤
├── base_cu.py           # BaseCU 增删改基类
├── query_helpers.py     # filtered_in_sql_values 等查询工具
└── event_listeners.py   # SQLAlchemy 事件监听
```

---

### CQ-04 [高] 企业微信同步/异步客户端大量并行重复

**位置**：`lush-wecom/src/lush_wecom/client/_sync/__init__.py` 与 `_async/__init__.py`（各约 800-900 行）

**推荐方案**：抽取共享调用描述为数据层，代码生成另一侧。

```python
# lush_wecom/client/_api_specs.py — 共享 API 定义
API_SPECS = {
    "send_message": {
        "method": "POST",
        "endpoint": "/cgi-bin/message/send",
        "body_builder": lambda params: params.model_dump(exclude_none=True),
    },
    # ...
}

# 通过装饰器或元类从 API_SPECS 生成 sync/async 方法
```

---

### CQ-05 [高] filtered_in_sql_values 在两个包中完全重复

**位置**：`lush-stdx/src/lush_stdx/itertoolsx.py` (9–30 行) 与 `lush-sqlalchemyx/base/dal/__init__.py` (35–56 行)

**推荐方案**：

```python
# lush-sqlalchemyx 中改为从 lush-stdx 导入
from lush_stdx.itertoolsx import filtered_in_sql_values
```

确保 `lush-sqlalchemyx` 的 `pyproject.toml` 已声明对 `lush-stdx` 的依赖（当前已有）。

---

### CQ-06 [高] JWT 异常处理通过 str(exc) 关键词分支

**位置**：`lush-exp/src/lush_exp/lush_security/jwt_manager.py` (256–298 行)

**推荐方案**：

```python
# 改为按异常类型分别捕获
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

def decrypt_model(self, token: str, ...):
    try:
        payload = jwt.decode(token, ...)
    except ExpiredSignatureError:
        raise TokenExpiredException("令牌已过期")
    except InvalidTokenError as e:
        raise TokenInvalidException("令牌无效")
```

---

### CQ-07 [中] 多处 except Exception 过宽

**涉及位置**（部分列举）：
- `lush-redisx/async_redis.py` health_check (~717 行)
- `lush-sqlalchemyx/mgrs/mysql/manager.py` health_check (~55 行)
- `lush-wecom/utils/media_validators.py` (~133, 162, 193 行)
- `lush-sentryx-core/sdk/v2/filters.py` transaction_filter (~118 行)

**推荐方案**：收窄异常范围至具体类型。

```python
# 示例：Redis health_check
async def health_check(self) -> bool:
    try:
        return await self._client.ping()
    except (RedisConnectionError, RedisTimeoutError, ConnectionRefusedError):
        return False
    # 不再捕获 Exception，让编程错误暴露
```

---

### CQ-08 [中] url_update_params 使用魔法下标

**位置**：`lush-stdx/src/lush_stdx/urllibx.py` (5–8 行)

**推荐方案**：

```python
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse

def url_update_params(url: str, params: dict) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    query.update(params)
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))
```

---

### CQ-09 [中] WeComClientBase JSON 解析失败文案不一致

**位置**：`lush-wecom/src/lush_wecom/core/base.py` (同步 ~271 行 vs 异步 ~466 行)

**推荐方案**：统一错误文案为同一常量。

```python
_JSON_PARSE_ERROR_MSG = "无法解析 API 响应为 JSON"
```

---

### CQ-10 [中] pydanticx empty_str_in_json_to_none 子串匹配不准确

**位置**：`lush-pydanticx/src/lush_pydanticx/__init__.py` (57–68 行)

**推荐方案**：

```python
import json

def empty_str_in_json_to_none(value: str) -> str | None:
    if not value or not value.strip():
        return None
    try:
        parsed = json.loads(value)
        if parsed == "" or parsed == [""]:
            return None
    except (json.JSONDecodeError, TypeError):
        pass
    return value
```

---

### CQ-11 [中] 文档语言风格不一致

**涉及**：多包公共 API 中英文 docstring 混用。

**推荐方案**：制定统一策略——公共 API 使用中文 docstring，或统一使用英文。在 CONTRIBUTING.md 或根目录 README 中明确规范。

---

### CQ-12 [低] wecom/core/base.py 中存在死代码

**位置**：`lush-wecom/src/lush_wecom/core/base.py` (38–39 行)

```python
with contextlib.suppress(ImportError):
    pass  # 无任何逻辑
```

**推荐方案**：删除此无效代码块。

---

## 三、漏洞/Bug

### BUG-01 [高] DebounceGuard 文档与实现不一致（实为节流）

**位置**：`lush-redisx/src/lush_redisx/integrations/fastapi/depends/rate_limit.py` (239–326 行)；`async_redis.py` `debounce_check_and_set`

**描述**：文档称"每次请求重置计时器"（防抖语义），实际用 `SET NX EX`（固定窗口节流），不会刷新 TTL。

**推荐方案**（二选一）：

```python
# 方案 A：实现真正的防抖（每次请求刷新 TTL）
async def debounce_check_and_set(self, key: str, ttl: int) -> DebounceResult:
    """真防抖：窗口内有新请求则重置计时器，静默期后才放行"""
    existed = await self._client.exists(key)
    await self._client.set(key, "1", ex=ttl)  # 每次都覆盖 TTL
    if existed:
        remaining = await self._client.ttl(key)
        return DebounceResult(allowed=False, remaining_seconds=float(remaining))
    return DebounceResult(allowed=True, remaining_seconds=0.0)

# 方案 B：承认当前行为为节流，重命名 API
# 将 DebounceGuard 重命名为 ThrottleGuard（或 FixedWindowGuard）
# 更新文档说明
```

---

### BUG-02 [高] 企业微信 Token httpx 客户端未提供生命周期管理

**位置**：`lush-wecom/src/lush_wecom/core/token_mgr.py` (21 行, 102 行)

**推荐方案**：

```python
class WeComTokenClient:
    def __init__(self, ...):
        self._client = httpx.Client(timeout=10)

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

class AsyncWeComTokenClient:
    async def aclose(self):
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.aclose()
```

---

### BUG-03 [中] JWT encrypt_model 的 expires_in 单位为小时而非分钟

**位置**：`lush-exp/src/lush_exp/lush_security/jwt_manager.py` (118–123 行)

**描述**：`timedelta(hours=expires_in)` 而 `default_expire_minutes` 暗示分钟单位，API 语义陷阱。

**推荐方案**：

```python
# 改为 minutes 并重命名参数
def encrypt_model(self, data, *, expires_in_minutes: int | None = None):
    exp = expires_in_minutes or self.config.default_expire_minutes
    payload["exp"] = datetime.now(UTC) + timedelta(minutes=exp)
```

---

### BUG-04 [中] 只读会话 SET TRANSACTION READ ONLY 失败被静默吞掉

**位置**：`lush-sqlalchemyx/src/lush_sqlalchemyx/mgrs/mysql/manager.py` (77–79 行)

**推荐方案**：

```python
@asynccontextmanager
async def got_readonly_session(self):
    async with self._session_factory() as session:
        try:
            await session.execute(sa.text("SET TRANSACTION READ ONLY"))
        except Exception:
            logger.error("无法设置只读事务，中止会话", exc_info=True)
            raise
        yield session
```

---

### BUG-05 [中] temporary_logging_config 退出后未恢复实际配置

**位置**：`lush-logx/src/lush_logx/logging.py` (342–362 行)

**描述**：文档称"自动恢复到原始配置"，实际只恢复 `_CONFIGURED`/`_CONFIG_LOCKED` 标志。

**推荐方案**：

```python
@contextmanager
def temporary_logging_config(config: LogConfig):
    import copy
    old_configured = _CONFIGURED
    old_locked = _CONFIG_LOCKED
    old_handlers = copy.copy(logging.root.handlers)
    old_level = logging.root.level

    try:
        _configure_logging(config)
        yield
    finally:
        globals()["_CONFIGURED"] = old_configured
        globals()["_CONFIG_LOCKED"] = old_locked
        logging.root.handlers = old_handlers
        logging.root.setLevel(old_level)
```

---

### BUG-06 [中] Sentry 敏感字段清理子串匹配导致误杀

**位置**：`lush-sentryx-core/src/lush_sentryx_core/sdk/v2/scrubbers.py` (51–53 行)

**推荐方案**：使用词边界匹配或精确匹配。

```python
import re

def _is_sensitive_key(key: str, denylist: list[str]) -> bool:
    key_lower = key.lower()
    return any(
        re.search(rf"(^|[_.\-]){re.escape(deny)}($|[_.\-])", key_lower)
        for deny in denylist
    )
```

---

### BUG-07 [低] Redis JSON 反序列化失败时返回原始字符串

**位置**：`lush-redisx/src/lush_redisx/async_redis.py` (633–637 行)

**推荐方案**：

```python
def _deserialize(self, value: bytes, mode: SerializationMode):
    if mode == SerializationMode.JSON:
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("JSON 反序列化失败: %s", e)
            return None  # 返回 None 而非损坏的字符串
```

---

## 四、竞态条件

### RACE-01 [高] Redis 互斥锁释放未校验持有者 token

**位置**：`lush-redisx/src/lush_redisx/integrations/fastapi/depends/mutex.py` (459–478 行)；`async_redis.py` `simple_distributed_lock` (642–662 行)

**描述**：加锁用 `SET key NX EX`，释放用无条件 `DELETE`。若业务耗时超过 TTL，键过期后另一请求获锁，原请求在 `finally` 中误删新持有者的锁。

**推荐方案**：

```python
import uuid

async def acquire_lock(self, key: str, timeout: int) -> str | None:
    token = str(uuid.uuid4())
    acquired = await self._client.set(key, token, nx=True, ex=timeout)
    return token if acquired else None

# Lua 脚本：原子比较+删除
_RELEASE_LOCK_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

async def release_lock(self, key: str, token: str) -> bool:
    result = await self._client.eval(_RELEASE_LOCK_SCRIPT, 1, key, token)
    return bool(result)
```

---

### RACE-02 [高] 企业微信 Token 并发刷新风暴

**位置**：`lush-wecom/src/lush_wecom/core/token_mgr.py` `get_token` (68–90 行, 149–171 行)

**描述**：多协程同时缓存未命中→并发请求微信 `gettoken`，浪费配额且可能触发频控。

**推荐方案**：

```python
import asyncio

class AsyncWeComTokenManager:
    def __init__(self, ...):
        self._refresh_lock = asyncio.Lock()

    async def get_token(self) -> str:
        cached = await self._storage.get()
        if cached:
            return cached

        async with self._refresh_lock:
            # 双重检查：获得锁后再查一次缓存
            cached = await self._storage.get()
            if cached:
                return cached
            token = await self._client.fetch_token()
            await self._storage.set(token, ttl=token.expires_in - 60)
            return token.access_token
```

---

### RACE-03 [中] cache_get_or_set 缓存击穿

**位置**：`lush-redisx/src/lush_redisx/async_redis.py` (203–229 行)

**推荐方案**：

```python
async def cache_get_or_set(self, key, producer, ttl, *, singleflight: bool = False):
    value = await self.get(key)
    if value is not None:
        return value

    if singleflight:
        lock_key = f"{key}:lock"
        acquired = await self._client.set(lock_key, "1", nx=True, ex=min(ttl, 30))
        if not acquired:
            # 另一协程正在计算，短暂等待后重试
            await asyncio.sleep(0.1)
            return await self.get(key) or await producer()

    value = await producer()
    await self.set(key, value, ttl=ttl)
    if singleflight:
        await self._client.delete(lock_key)
    return value
```

---

### RACE-04 [中] 日志配置路径无锁保护

**位置**：`lush-logx/src/lush_logx/logging.py` `_configure_logging` (307–335 行)

**推荐方案**：

```python
import threading

_CONFIG_LOCK = threading.Lock()

def configure_logging_once(config: LogConfig):
    with _CONFIG_LOCK:
        if _CONFIGURED:
            return
        _configure_logging(config)
```

---

## 五、测试不稳定性

### FLAKY-01 [Critical] SQLite 测试使用固定文件路径

**位置**：`lush-sqlalchemyx/tests/test_base_dal.py` (211–250 行)；`tests/test_config.yaml` 中 `TEST_SQLITE_PATH: .tmp/lush_sqlalchemyx_test.db`

**描述**：pytest-xdist 并行或多 CI job 时共享同一文件，导致锁/损坏/随机失败。

**推荐方案**：

```python
@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")

@pytest.fixture
async def db_manager(db_path):
    manager = AsyncMySQLManager(f"sqlite+aiosqlite:///{db_path}")
    yield manager
    await manager.close()
```

---

### FLAKY-02 [高] Redis 测试大量使用 sleep 等待过期

**位置**：`lush-redisx/tests/test_manager.py` (多处 `asyncio.sleep(1.1/2.1)`)；`tests/integrations/fastapi/test_rate_limit.py` (~354 行)

**推荐方案**：

```python
# 改为轮询 + 超时
import time

async def wait_until(predicate, timeout=5.0, interval=0.1):
    """轮询直到 predicate() 为 True 或超时"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if await predicate():
            return True
        await asyncio.sleep(interval)
    raise TimeoutError(f"等待超过 {timeout}s")

# 使用
await wait_until(lambda: redis_mgr.get("key") is None, timeout=5.0)
```

---

### FLAKY-03 [高] Sentry 测试直接 sentry_sdk.init 无 teardown

**位置**：`lush-sentryx/tests/test_sentryx.py` (~921–927 行)

**推荐方案**：

```python
@pytest.fixture(autouse=True)
def _isolate_sentry():
    """每个测试后重置 Sentry 全局状态"""
    yield
    client = sentry_sdk.Hub.current.client
    if client:
        client.close()
    sentry_sdk.Hub.current.bind_client(None)
    sentry_sdk.Hub.main.bind_client(None)
```

---

### FLAKY-04 [中] Redis 测试使用固定 key 名

**位置**：`lush-redisx/tests/test_manager.py` 各处

**推荐方案**：

```python
@pytest.fixture
def unique_prefix():
    return f"test:{uuid.uuid4().hex[:8]}:"

# 在测试中使用
async def test_set_get(redis_mgr, unique_prefix):
    key = f"{unique_prefix}mykey"
    await redis_mgr.set(key, "value")
    # ...
```

---

### FLAKY-05 [中] 不可达 DSN 测试依赖 TCP 超时

**位置**：`lush-sentryx/tests/test_sentryx.py` (~241–262 行)

**推荐方案**：patch 传输层，不依赖真实网络。

```python
def test_capture_with_unreachable_dsn(monkeypatch):
    transport = unittest.mock.MagicMock()
    monkeypatch.setattr(sentry_sdk.transport, "HttpTransport", lambda *a, **kw: transport)
    # ...
```

---

### FLAKY-06 [中] 乐观锁并发测试用 sleep 赌交错

**位置**：`lush-sqlalchemyx/tests/test_base_dal.py` (~3290–3343 行)

**推荐方案**：使用 `asyncio.Event` 或 `asyncio.Barrier` 替代 `sleep(0.01)` 控制交错。

```python
async def test_concurrent_updates_with_version_conflict():
    barrier = asyncio.Barrier(2)

    async def task_a():
        record = await dal.get(id)
        await barrier.wait()  # 同步点：两个 task 同时持有旧版本
        await dal.update(record)

    async def task_b():
        record = await dal.get(id)
        await barrier.wait()
        await dal.update(record)

    results = await asyncio.gather(task_a(), task_b(), return_exceptions=True)
    assert any(isinstance(r, OptimisticLockError) for r in results)
```

---

### FLAKY-07 [中] 防抖/节流时间窗口断言过窄

**位置**：`lush-redisx/tests/test_manager.py` (~988–1008 行)

**推荐方案**：放宽容差或改为断言单调性。

```python
# 改为
assert result2.remaining_seconds > 0
assert result3.remaining_seconds < result2.remaining_seconds
```

---

## 六、代码可维护性与命令重复

### MAINT-01 [Critical] 10 个包级 justfile 除注释外完全相同

**涉及文件**：全部 `lush-*/justfile`（10 份）

**描述**：`lock`/`sync`/`test`/`build`/`clean`/`fmt`/`lint`/`lint-fix`/`version`/`set-version`/`bump` 等 recipe 在 10 份文件中逐字重复，仅第 3 行包名注释不同。

**推荐方案**：

```
# 方案 A：Just import（推荐，需 just >= 1.19）
# 根目录新增 just/package.just，内含全部公共 recipe
# 各包 justfile 简化为：

import '../just/package.just'

# 仅保留包级特殊 recipe（若有）
```

```
# 方案 B：符号链接（更简单）
# 所有包的 justfile 指向同一份模板

cd lush-stdx && ln -sf ../just/package.just justfile
cd lush-logx && ln -sf ../just/package.just justfile
# ... 重复 10 次，或用脚本
```

```just
# just/package.just — 共享模板内容
python := "3.10"
default_index := "https://pypi.org/simple"

lock:
    uv lock -p {{python}}

sync:
    uv sync -p {{python}}

test *args:
    uv run -p {{python}} pytest {{args}}

build:
    uv build

clean:
    rm -rf dist .pytest_cache .ruff_cache

fmt:
    uvx ruff format .

lint:
    uvx ruff check .

lint-fix:
    uvx ruff check --fix .

version:
    @grep '^version' pyproject.toml | head -1

# ... bump/set-version 等
```

---

### MAINT-02 [Critical] Ruff 配置在 10 个 pyproject.toml 中逐字重复

**涉及文件**：全部 `lush-*/pyproject.toml` 中 `[tool.ruff]`/`[tool.ruff.lint]`/`[tool.ruff.format]`

**描述**：`line-length`、`target-version`、`select = ["ALL"]`、数百行 `ignore` 列表、`per-file-ignores`、`format` 块大面积复制。

**推荐方案**：

```toml
# 根目录新增 ruff.toml（共享基线）
line-length = 120
target-version = "py310"

[lint]
select = ["ALL"]
ignore = [
    "D",       # docstring（统一策略）
    "ANN",     # annotations
    "ERA001",  # commented-out code
    # ... 其余全局 ignore
]

[lint.per-file-ignores]
"tests/**/*.py" = ["S101", "PLR2004", "ANN"]

[format]
quote-style = "double"
indent-style = "space"
```

```toml
# 各包 pyproject.toml — 仅保留包级差异
[tool.ruff]
extend = "../ruff.toml"

# lush-wecom 额外
[tool.ruff.lint.per-file-ignores]
"src/lush_wecom/tests/**/*.py" = ["S101", "PLR2004"]
"__script_*.py" = ["ALL"]
```

---

### MAINT-03 [高] basedpyright "tests 宽松"配置各包不一致

**涉及文件**：各包 `pyproject.toml` 中 `[[tool.basedpyright.executionEnvironments]]`

**描述**：各包 tests 环境的 `report*=none` 键集合长度和内容不同，产生无意义漂移。

**推荐方案**：

```toml
# 文档化标准 tests 宽松基线，各包统一使用
# 可在根目录维护 basedpyright-tests-baseline.toml 作为参考

[[tool.basedpyright.executionEnvironments]]
root = "tests"
reportMissingImports = "none"
reportMissingTypeStubs = "none"
reportUnknownMemberType = "none"
reportUnknownVariableType = "none"
reportUnknownArgumentType = "none"
reportUnknownParameterType = "none"
reportUnusedImport = "none"
reportCallIssue = "none"
reportIndexIssue = "none"
reportOperatorIssue = "none"
reportAttributeAccessIssue = "none"
reportReturnType = "none"
reportArgumentType = "none"
reportAssignmentType = "none"
# ↑ 统一此列表，各包直接复制，不再随意增减
```

---

### MAINT-04 [高] Pytest 配置重复且 lush-logx 与其他包不一致

**涉及文件**：各包 `pyproject.toml` 中 `[tool.pytest.ini_options]`

**描述**：`asyncio_mode = "auto"` 等在多数包相同；`lush-logx` 无 `pytest-asyncio` 依赖且无 asyncio 配置项。

**推荐方案**：若 `lush-logx` 确无异步测试，在 pyproject.toml 中加注释说明；否则对齐。统一 pytest 配置可通过 `conftest.py` 层级继承或文档化标准模板。

---

### MAINT-05 [中] lush-wecom 测试放在 src 树下

**位置**：`lush-wecom/src/lush_wecom/tests/`（其余 9 包为顶层 `tests/`）

**推荐方案**（二选一）：
- **长期**：迁移到顶层 `tests/` 与其他包一致
- **短期**：在 `lush-wecom/CONTRIBUTING.md` 中明确说明原因，并确保 Ruff/basedpyright 路径配置覆盖

---

### MAINT-06 [低] pyproject.toml 区块顺序不统一

**推荐方案**：统一各包区块顺序为：

```
[project]
[build-system]
[tool.uv]
[dependency-groups]
[tool.pytest.ini_options]
[tool.ruff] / [tool.ruff.lint] / [tool.ruff.format]
[tool.basedpyright]
[tool.coverage]  # 仅需要时
```

---

## 七、优先级总览与推荐解决方案

### P0 — 立即修复

| 编号 | 类别 | 问题 | 预计工作量 |
|------|------|------|-----------|
| SEC-01 | 安全 | SSRF 防护 — URL 校验函数 | 2h |
| RACE-01 | 竞态 | Redis 锁释放加 token + Lua 脚本 | 3h |
| SEC-02 | 安全 | 禁止加密模式下明文 ID 回退 | 1h |
| CQ-02 | 质量 | LogConfig.level 加 `.upper()` | 15min |
| CQ-01 | 质量 | Sentry filter 异常时返回原事件而非 None | 30min |
| MAINT-01 | 维护 | **10 个 justfile 合并为共享模板** | 2h |
| MAINT-02 | 维护 | **Ruff 配置抽取到根目录 ruff.toml** | 3h |

### P1 — 短期修复（1-2 周）

| 编号 | 类别 | 问题 | 预计工作量 |
|------|------|------|-----------|
| BUG-01 | 漏洞 | DebounceGuard 实现真防抖或重命名 | 3h |
| FLAKY-01 | 测试 | SQLite 路径改 tmp_path | 1h |
| FLAKY-02 | 测试 | Redis 测试 sleep 改轮询 | 4h |
| RACE-02 | 竞态 | Token 并发刷新加锁 | 2h |
| CQ-05 | 质量 | filtered_in_sql_values 去重 | 30min |
| BUG-02 | 漏洞 | httpx 客户端生命周期管理 | 2h |
| FLAKY-03 | 测试 | Sentry 测试隔离 | 2h |
| MAINT-03 | 维护 | basedpyright 统一基线 | 2h |

### P2 — 中期改进（1-2 月）

| 编号 | 类别 | 问题 | 预计工作量 |
|------|------|------|-----------|
| SEC-04 | 安全 | Redis fail-open 可配置策略 | 3h |
| SEC-05 | 安全 | XFF IP 信任模型改进 | 2h |
| CQ-03 | 质量 | dal/__init__.py 拆分子模块 | 8h |
| CQ-04 | 质量 | 企业微信客户端代码生成 | 16h |
| BUG-03 | 漏洞 | JWT expires_in 单位修复 | 1h |
| RACE-03 | 竞态 | cache_get_or_set singleflight | 3h |
| MAINT-04 | 维护 | Pytest 配置对齐 | 2h |
| MAINT-05 | 维护 | lush-wecom 测试目录迁移 | 4h |

### P3 — 长期优化

| 编号 | 类别 | 问题 | 预计工作量 |
|------|------|------|-----------|
| CQ-07 | 质量 | 全局收窄 except Exception | 4h |
| CQ-06 | 质量 | JWT 按异常类型分别捕获 | 2h |
| SEC-07 | 安全 | CSP 默认 strict | 1h |
| CQ-11 | 质量 | 文档语言统一 | 4h |
| MAINT-06 | 维护 | pyproject.toml 区块顺序统一 | 2h |

---

> **统计**：共发现 **68 项**问题（安全 12 / 代码质量 12 / 漏洞 7 / 竞态 8 / 测试 7 / 可维护性 6），其中 Critical 4 项、High 16 项、Medium 30 项、Low 18 项。
