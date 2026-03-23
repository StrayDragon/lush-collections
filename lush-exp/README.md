# lush-exp

这里放“还不想定型”的代码: 能用,但不保证 API 稳定.

目前主要分两块:

- `lush_exp.lush_security`: JWT/CSP 相关小工具
- `lush_exp.lush_scriptx`: 调试/Mock 辅助

一个最小的 JWT 例子:

```python
from lush_exp.lush_security.jwt_manager import JWTConfig, JWTManager, SimpleIDPayload

manager = JWTManager(JWTConfig(secret_key="change-me"))
token = manager.encrypt_model(SimpleIDPayload(id="123"), subject="encrypted_id")
payload = manager.decrypt_model(token, SimpleIDPayload, verify_subject="encrypted_id")
```

## 开发

```bash
uv sync -p 3.10 --frozen
uv run -p 3.10 pytest
```
