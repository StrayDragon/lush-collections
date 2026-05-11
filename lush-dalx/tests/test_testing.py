"""testing 模块测试 — 验证一致性测试套件自身可用."""

from lush_dalx.testing import AsyncDALConformanceTests, SyncDALConformanceTests


class TestConformanceSuitesExist:
    def test_sync_suite_has_test_methods(self):
        methods = [m for m in dir(SyncDALConformanceTests) if m.startswith("test_")]
        assert len(methods) >= 15

    def test_async_suite_has_test_methods(self):
        methods = [m for m in dir(AsyncDALConformanceTests) if m.startswith("test_")]
        assert len(methods) >= 13

    def test_sync_suite_methods_match_protocol(self):
        expected = {
            "test_create_returns_entity",
            "test_create_no_refresh",
            "test_get_by_id_existing",
            "test_get_by_id_nonexistent",
            "test_ret_dto_after_get_by_id",
            "test_ret_dto_after_get_by_id_nonexistent",
            "test_get_all_default_pagination",
            "test_get_all_with_pagination",
            "test_count_returns_int",
            "test_exists_true_for_existing",
            "test_exists_false_for_nonexistent",
            "test_batch_get_id__entity",
            "test_batch_get_id__dto",
            "test_ret_dto_after_create",
            "test_update_only_set_by_id_existing",
            "test_update_only_set_by_id_nonexistent",
            "test_delete_by_id_existing",
            "test_delete_by_id_nonexistent",
            "test_delete_then_get_returns_none",
            "test_iter_record_dtos_yields",
        }
        actual = {m for m in dir(SyncDALConformanceTests) if m.startswith("test_")}
        assert expected == actual

    def test_async_suite_methods_match_protocol(self):
        expected = {
            "test_create_returns_entity",
            "test_create_no_refresh",
            "test_get_by_id_existing",
            "test_get_by_id_nonexistent",
            "test_ret_dto_after_get_by_id",
            "test_ret_dto_after_get_by_id_nonexistent",
            "test_get_all_default_pagination",
            "test_count_returns_int",
            "test_exists_true_for_existing",
            "test_exists_false_for_nonexistent",
            "test_batch_get_id__entity",
            "test_batch_get_id__dto",
            "test_ret_dto_after_create",
            "test_update_only_set_by_id_existing",
            "test_update_only_set_by_id_nonexistent",
            "test_delete_by_id_existing",
            "test_delete_by_id_nonexistent",
        }
        actual = {m for m in dir(AsyncDALConformanceTests) if m.startswith("test_")}
        assert expected == actual
