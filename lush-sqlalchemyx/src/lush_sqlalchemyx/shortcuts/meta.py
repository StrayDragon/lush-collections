# pragma: no cover
import dataclasses
from collections.abc import Callable
from typing import cast

from sqlalchemy import Dialect, Table
from sqlalchemy.dialects.mysql import dialect as mysql_dialect
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.schema import CreateIndex, CreateTable
from sqlalchemy.sql.compiler import Compiled


@dataclasses.dataclass
class TableDDLInfo:
    """DDL 元数据容器."""

    create_table: Compiled
    index_ddls: list[Compiled]

    def print_sql(self) -> None:
        """打印 CREATE TABLE + CREATE INDEX SQL."""
        output = str(self.create_table)
        if not output.endswith(";"):
            output += ";"
        print(output)
        for index_ddl in self.index_ddls:
            index_ddl_sql = str(index_ddl)
            if not index_ddl_sql.endswith(";"):
                index_ddl_sql = index_ddl_sql + ";"
            print(index_ddl_sql)
        print()


def get_table_ddl_info(
    entity: type[DeclarativeBase],
    dialect_fn: Callable[[], Dialect | None] = mysql_dialect,
) -> TableDDLInfo:
    dialect = dialect_fn()
    table = cast("Table", entity.__table__)
    stmt = CreateTable(table)

    index_ddls: list[Compiled] = []
    for index in table.indexes:
        create_index = CreateIndex(index)
        index_ddl = create_index.compile(dialect=dialect, compile_kwargs={"literal_binds": True})
        index_ddls.append(index_ddl)
    return TableDDLInfo(
        create_table=stmt.compile(dialect=dialect, compile_kwargs={"literal_binds": True}),
        index_ddls=index_ddls,
    )
