"""Shared pytest fixtures for integration-ish tests.

Goals:
- Connect to docker compose bridge MySQL services (mysql57 / mysql8).
- Run via ``just test-docker lush-sqlalchemyx``.
- Idempotent cleanup; refuse non-test DB names / unsafe hosts.
- Matrix: MySQL 5.7 / 8 endpoints + SESSION sql_mode helpers.
"""

from __future__ import annotations

import os
import re
import time
import uuid
from collections.abc import Generator
from dataclasses import dataclass

import pytest

_TEST_DB_NAME_PATTERN = re.compile(r"^lush_test_[a-f0-9]+$")
_COMPOSE_HOSTS = frozenset({"mysql57", "mysql8", "mysql"})

MYSQL57_IMAGE_DEFAULT = "mysql:5.7"
MYSQL8_IMAGE_DEFAULT = "mysql:8.0.40-debian"

MYSQL_SQL_MODE_NONSTRICT = "NO_ENGINE_SUBSTITUTION"
MYSQL_SQL_MODE_STRICT = (
    "ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION"
)


@dataclass(frozen=True, slots=True)
class _MySQLEndpoint:
    host: str
    port: int
    user: str
    password: str
    database: str
    image: str | None = None

    @property
    def sqlalchemy_url(self) -> str:
        return f"mysql+aiomysql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"

    @property
    def sync_sqlalchemy_url(self) -> str:
        return f"mysql+pymysql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


def _validate_test_endpoint(endpoint: _MySQLEndpoint) -> None:
    if endpoint.host not in _COMPOSE_HOSTS:
        raise RuntimeError(
            f"SAFETY: test endpoint host '{endpoint.host}' is not allowed. "
            "Use docker compose test infra (mysql57 / mysql8)."
        )
    if not _TEST_DB_NAME_PATTERN.match(endpoint.database):
        raise RuntimeError(f"SAFETY: database name '{endpoint.database}' does not match test pattern 'lush_test_<hex>'.")


def _mysql_root_password() -> str:
    return os.getenv("LUSH_TEST_MYSQL_ROOT_PASSWORD", "lush_test_root")


def _mysql_port() -> int:
    raw = os.getenv("LUSH_TEST_MYSQL_PORT")
    return 3306 if raw is None else int(raw)


def _mysql57_image() -> str:
    return os.getenv("LUSH_TEST_MYSQL57_IMAGE", MYSQL57_IMAGE_DEFAULT)


def _mysql8_image() -> str:
    return os.getenv("LUSH_TEST_MYSQL8_IMAGE", MYSQL8_IMAGE_DEFAULT)


def _wait_for_mysql_tcp_ready(host: str, port: int, password: str, *, timeout_s: float = 90.0) -> None:
    import pymysql

    deadline = time.time() + timeout_s
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            conn = pymysql.connect(host=host, port=port, user="root", password=password, connect_timeout=2)
            conn.close()
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(0.5)
    raise RuntimeError(
        f"MySQL not ready at {host}:{port}: {last_error}. "
        "Start compose infra: just test-docker lush-sqlalchemyx"
    )


def _mysql_exec_sql(host: str, port: int, password: str, sql: str) -> None:
    import pymysql

    conn = pymysql.connect(host=host, port=port, user="root", password=password)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    finally:
        conn.close()


def _compose_mysql_endpoint(host: str, *, image: str) -> Generator[_MySQLEndpoint, None, None]:
    password = _mysql_root_password()
    port = _mysql_port()
    database = f"lush_test_{uuid.uuid4().hex[:12]}"
    _wait_for_mysql_tcp_ready(host, port, password, timeout_s=90.0)
    _mysql_exec_sql(host, port, password, f"CREATE DATABASE `{database}`;")
    ep = _MySQLEndpoint(
        host=host,
        port=port,
        user="root",
        password=password,
        database=database,
        image=image,
    )
    _validate_test_endpoint(ep)
    try:
        yield ep
    finally:
        _mysql_exec_sql(host, port, password, f"DROP DATABASE IF EXISTS `{database}`;")


@pytest.fixture(scope="session")
def mysql_endpoint() -> Generator[_MySQLEndpoint, None, None]:
    host = os.getenv("LUSH_TEST_MYSQL_HOST", os.getenv("LUSH_TEST_MYSQL8_HOST", "mysql8"))
    yield from _compose_mysql_endpoint(host, image=os.getenv("LUSH_TEST_MYSQL_IMAGE", MYSQL8_IMAGE_DEFAULT))


@pytest.fixture(scope="session")
def mysql57_endpoint() -> Generator[_MySQLEndpoint, None, None]:
    yield from _compose_mysql_endpoint(os.getenv("LUSH_TEST_MYSQL57_HOST", "mysql57"), image=_mysql57_image())


@pytest.fixture(scope="session")
def mysql8_endpoint() -> Generator[_MySQLEndpoint, None, None]:
    yield from _compose_mysql_endpoint(os.getenv("LUSH_TEST_MYSQL8_HOST", "mysql8"), image=_mysql8_image())


# hypothesis 属性测试配置 (docs/design/11 §4)
if os.getenv("CI"):
    from hypothesis import settings

    settings.register_profile("ci", derandomize=True)
    settings.load_profile("ci")
