"""Tests for shortcuts.meta utilities."""

from sqlalchemy import Index, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from lush_sqlalchemyx.shortcuts.meta import TableDDLInfo, get_table_ddl_info


class _Base(DeclarativeBase):
    pass


class _MetaExample(_Base):
    __tablename__ = "unit_testing_meta_example"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)

    __table_args__ = (Index("idx_unit_testing_meta_example_name", "name"),)


def test_get_table_ddl_info_compiles_table_and_index():
    info = get_table_ddl_info(_MetaExample)

    create_sql = str(info.create_table)
    assert "CREATE TABLE" in create_sql.upper()
    assert "unit_testing_meta_example" in create_sql

    assert len(info.index_ddls) == 1
    index_sql = str(info.index_ddls[0])
    assert "CREATE" in index_sql.upper()
    assert "INDEX" in index_sql.upper()
    assert "idx_unit_testing_meta_example_name" in index_sql


def test_table_ddl_info_print_sql_outputs_statements(capsys):
    info = get_table_ddl_info(_MetaExample)
    info.print_sql()

    captured = capsys.readouterr().out
    assert "CREATE TABLE" in captured.upper()
    assert "CREATE INDEX" in captured.upper()


class _MetaExampleNoSpecialFields(_Base):
    __tablename__ = "unit_testing_meta_example_no_special_fields"

    pk: Mapped[int] = mapped_column(Integer, primary_key=True)
    nickname: Mapped[str] = mapped_column(String(50), nullable=False)


def test_print_sql_does_not_reorder_when_no_special_fields(capsys):
    info = get_table_ddl_info(_MetaExampleNoSpecialFields)
    info.print_sql()

    captured = capsys.readouterr().out
    assert "CREATE TABLE" in captured.upper()
    assert "unit_testing_meta_example_no_special_fields" in captured


def test_print_sql_does_not_append_semicolon_when_already_present(capsys):
    class _DummyCompiled:
        def __init__(self, sql: str) -> None:
            self._sql = sql

        def __str__(self) -> str:
            return self._sql

    info = TableDDLInfo(
        create_table=_DummyCompiled("CREATE TABLE t (id INT);\n"),
        index_ddls=[_DummyCompiled("CREATE INDEX idx_t_id ON t (id);")],
    )
    info.print_sql()

    captured = capsys.readouterr().out
    assert "CREATE TABLE" in captured.upper()
    assert "CREATE INDEX" in captured.upper()
    assert ";;" not in captured
