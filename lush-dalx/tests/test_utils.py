"""utils 模块测试."""

from lush_dalx.utils import escape_like, filtered_in_sql_values


class TestFilteredInSqlValues:
    def test_none_input(self):
        assert filtered_in_sql_values(None) == []

    def test_empty_input(self):
        assert filtered_in_sql_values([]) == []

    def test_basic(self):
        assert filtered_in_sql_values([1, 2, 3]) == [1, 2, 3]

    def test_dedup(self):
        assert filtered_in_sql_values([1, 2, 2, 3, 1]) == [1, 2, 3]

    def test_skip_none_and_empty(self):
        assert filtered_in_sql_values([1, None, "", 2]) == [1, 2]

    def test_type_conversion(self):
        result = filtered_in_sql_values(["1", "2", "3"], target_type_as=int)
        assert result == [1, 2, 3]

    def test_type_conversion_error_skipped(self):
        result = filtered_in_sql_values(["1", "abc", "3"], target_type_as=int)
        assert result == [1, 3]


class TestEscapeLike:
    def test_no_special(self):
        v, esc = escape_like("hello")
        assert v == "hello"
        assert esc == "\\"

    def test_percent(self):
        v, _ = escape_like("50%")
        assert v == "50\\%"

    def test_underscore(self):
        v, _ = escape_like("a_b")
        assert v == "a\\_b"

    def test_backslash(self):
        v, _ = escape_like("a\\b")
        assert v == "a\\\\b"

    def test_custom_escape(self):
        v, esc = escape_like("a%b_c", escape_char="!")
        assert v == "a!%b!_c"
        assert esc == "!"
