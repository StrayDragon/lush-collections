"""protocols 模块测试.

验证 Protocol 的 runtime_checkable 行为和基本结构完整性.
"""

from collections.abc import AsyncIterator, Iterator

from lush_dal_protocol.protocols import (
    AsyncBaseDALProtocol,
    AsyncReadDALProtocol,
    AsyncWriteDALProtocol,
    SyncBaseDALProtocol,
    SyncReadDALProtocol,
    SyncWriteDALProtocol,
)


class _FakeSession:
    pass


class _FakeEntity:
    pass


class _FakeDTO:
    pass


class _FakeCU:
    pass


class _SyncReadImpl:
    @classmethod
    def get_by_id(cls, session, entity_id):
        return None

    @classmethod
    def get_all(cls, session, skip=0, limit=100):
        return []

    @classmethod
    def count(cls, session):
        return 0

    @classmethod
    def exists(cls, session, entity_id):
        return False

    @classmethod
    def ret_dto_after_get_by_id(cls, session, entity_id, need_refresh=True):
        return None

    @classmethod
    def batch_get_id__entity(cls, session, entity_ids):
        return {}

    @classmethod
    def batch_get_id__dto(cls, session, entity_ids):
        return {}

    @classmethod
    def iter_record_dtos(cls, session, *, batch_size=500) -> Iterator:
        return iter([])


class _SyncWriteImpl:
    @classmethod
    def create(cls, session, cu, need_refresh=True):
        return _FakeEntity()

    @classmethod
    def ret_dto_after_create(cls, session, cu, need_refresh=True):
        return _FakeDTO()

    @classmethod
    def update_only_set_by_id(cls, session, entity_id, cu, need_refresh=False):
        return None

    @classmethod
    def delete_by_id(cls, session, entity_id):
        return True


class _SyncBaseImpl(_SyncReadImpl, _SyncWriteImpl):
    pass


class _AsyncReadImpl:
    @classmethod
    async def get_by_id(cls, session, entity_id):
        return None

    @classmethod
    async def get_all(cls, session, skip=0, limit=100):
        return []

    @classmethod
    async def count(cls, session):
        return 0

    @classmethod
    async def exists(cls, session, entity_id):
        return False

    @classmethod
    async def ret_dto_after_get_by_id(cls, session, entity_id, need_refresh=True):
        return None

    @classmethod
    async def batch_get_id__entity(cls, session, entity_ids):
        return {}

    @classmethod
    async def batch_get_id__dto(cls, session, entity_ids):
        return {}

    @classmethod
    async def iter_record_dtos(cls, session, *, batch_size=500) -> AsyncIterator:
        return
        yield


class _AsyncWriteImpl:
    @classmethod
    async def create(cls, session, cu, need_refresh=True):
        return _FakeEntity()

    @classmethod
    async def ret_dto_after_create(cls, session, cu, need_refresh=True):
        return _FakeDTO()

    @classmethod
    async def update_only_set_by_id(cls, session, entity_id, cu, need_refresh=False):
        return None

    @classmethod
    async def delete_by_id(cls, session, entity_id):
        return True


class _AsyncBaseImpl(_AsyncReadImpl, _AsyncWriteImpl):
    pass


class TestSyncProtocols:
    def test_sync_read_isinstance(self):
        assert isinstance(_SyncReadImpl, SyncReadDALProtocol)

    def test_sync_write_isinstance(self):
        assert isinstance(_SyncWriteImpl, SyncWriteDALProtocol)

    def test_sync_base_isinstance(self):
        assert isinstance(_SyncBaseImpl, SyncBaseDALProtocol)

    def test_sync_read_not_match(self):
        assert not isinstance(object(), SyncReadDALProtocol)


class TestAsyncProtocols:
    def test_async_read_isinstance(self):
        assert isinstance(_AsyncReadImpl, AsyncReadDALProtocol)

    def test_async_write_isinstance(self):
        assert isinstance(_AsyncWriteImpl, AsyncWriteDALProtocol)

    def test_async_base_isinstance(self):
        assert isinstance(_AsyncBaseImpl, AsyncBaseDALProtocol)

    def test_async_read_not_match(self):
        assert not isinstance(object(), AsyncReadDALProtocol)
