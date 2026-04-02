from __future__ import annotations

import pytest

from lush_wecom.core.storage import AsyncMemoryStorage, MemoryStorage
from lush_wecom.core.token_mgr import (
    AsyncWeComTokenClient,
    AsyncWeComTokenManager,
    WeComTokenClient,
    WeComTokenManager,
)


def test_token_client_mock_mode() -> None:
    client = WeComTokenClient("", "", mock_enabled=True)
    resp = client.get_access_token()
    assert resp.errcode == 0
    assert resp.access_token == "wecom-mock-token"


def test_token_client_requires_corp_creds_when_not_mock() -> None:
    with pytest.raises(ValueError):
        _ = WeComTokenClient("", "", mock_enabled=False)


def test_token_manager_cache_and_refresh_in_mock_mode() -> None:
    storage = MemoryStorage()
    mgr = WeComTokenManager("id", "sec", storage=storage, mock_enabled=True)

    # First call stores in cache
    token1 = mgr.get_token()
    assert token1

    # Second call hits cache
    token2 = mgr.get_token()
    assert token2 == token1

    # Force refresh bypasses cache (mock token stays the same)
    token3 = mgr.get_token(force_refresh=True)
    assert token3 == token1


@pytest.mark.asyncio
async def test_async_token_client_and_manager_mock_and_cache() -> None:
    client = AsyncWeComTokenClient("", "", mock_enabled=True)
    resp = await client.get_access_token()
    assert resp.access_token == "wecom-mock-token"

    with pytest.raises(ValueError):
        _ = AsyncWeComTokenClient("", "", mock_enabled=False)

    mgr = AsyncWeComTokenManager("id", "sec", storage=AsyncMemoryStorage(), mock_enabled=True)
    token1 = await mgr.get_token()
    token2 = await mgr.get_token()
    assert token2 == token1
