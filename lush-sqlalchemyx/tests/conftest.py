"""Shared pytest fixtures for integration-ish tests.

Goals:
- Automatically provision external dependencies (e.g. MySQL) via Docker.
- Prefer local images; optional ``LUSH_TEST_MYSQL_PULL=1`` to pull.
- Idempotent cleanup; refuse non-localhost / non-test DB names.
- Matrix: MySQL 5.7 / 8 endpoints + SESSION sql_mode helpers.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
import uuid
from collections.abc import Generator, Sequence
from dataclasses import dataclass

import pytest

_TEST_DB_NAME_PATTERN = re.compile(r"^lush_test_[a-f0-9]+$")
_TEST_CONTAINER_NAME_PATTERN = re.compile(r"^lush-sqlalchemyx-mysql-pytest-[a-f0-9]+$")
_SAFE_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

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
    container_name: str | None = None
    image: str | None = None

    @property
    def sqlalchemy_url(self) -> str:
        return f"mysql+aiomysql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"

    @property
    def sync_sqlalchemy_url(self) -> str:
        return f"mysql+pymysql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


def _validate_test_endpoint(endpoint: _MySQLEndpoint) -> None:
    if endpoint.host not in _SAFE_HOSTS:
        raise RuntimeError(
            f"SAFETY: test endpoint host '{endpoint.host}' is not localhost. Refusing to run tests against a remote database."
        )
    if not _TEST_DB_NAME_PATTERN.match(endpoint.database):
        raise RuntimeError(f"SAFETY: database name '{endpoint.database}' does not match test pattern 'lush_test_<hex>'.")
    if endpoint.container_name and not _TEST_CONTAINER_NAME_PATTERN.match(endpoint.container_name):
        raise RuntimeError(f"SAFETY: container name '{endpoint.container_name}' does not match test pattern.")


def _docker_available() -> bool:
    docker = shutil.which("docker")
    if docker is None:
        return False
    try:
        return (
            subprocess.run(  # noqa: S603
                [docker, "ps"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            ).returncode
            == 0
        )
    except OSError:
        return False


def _docker_image_exists(image: str) -> bool:
    docker = shutil.which("docker")
    if docker is None:
        return False
    try:
        return (
            subprocess.run(  # noqa: S603
                [docker, "image", "inspect", image],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            ).returncode
            == 0
        )
    except OSError:
        return False


def _docker_pull_if_needed(image: str) -> None:
    if _docker_image_exists(image):
        return
    if os.getenv("LUSH_TEST_MYSQL_PULL", "").strip().lower() not in {"1", "true", "yes"}:
        return
    docker = shutil.which("docker")
    if docker is None:
        return
    subprocess.run([docker, "pull", image], check=True, text=True)  # noqa: S603


def _choose_mysql_image() -> str:
    if env_image := os.getenv("LUSH_TEST_MYSQL_IMAGE"):
        return env_image
    candidates = [
        MYSQL57_IMAGE_DEFAULT,
        "mysql:5.7.42-debian",
        MYSQL8_IMAGE_DEFAULT,
        "mysql:8.0",
        "mysql:8",
        "mysql:8.4",
    ]
    for image in candidates:
        if _docker_image_exists(image):
            return image
    return MYSQL8_IMAGE_DEFAULT


def _mysql57_image() -> str:
    return os.getenv("LUSH_TEST_MYSQL57_IMAGE", MYSQL57_IMAGE_DEFAULT)


def _mysql8_image() -> str:
    return os.getenv("LUSH_TEST_MYSQL8_IMAGE", MYSQL8_IMAGE_DEFAULT)


def _docker_rm_if_exists(container_name: str) -> None:
    docker = shutil.which("docker")
    if docker is None:
        return
    subprocess.run(  # noqa: S603
        [docker, "rm", "-f", container_name],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )


def _mysql_server_command_args(image: str) -> list[str]:
    """MySQL 8.0 可用 native password; 8.4+ / 浮动 ``mysql:8`` 不可再传该参数."""
    tag = image.split(":", maxsplit=1)[-1]
    if tag.startswith("8.0") or "8.0." in tag:
        return ["--default-authentication-plugin=mysql_native_password"]
    return []


def _docker_start_mysql(
    container_name: str,
    *,
    image: str,
    root_password: str,
    database: str,
    server_args: Sequence[str] | None = None,
) -> int:
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError("Docker is unavailable")
    _docker_rm_if_exists(container_name)
    cmd = [
        docker,
        "run",
        "--rm",
        "-d",
        "--name",
        container_name,
        "-e",
        "MYSQL_ROOT_HOST=%",
        "-e",
        f"MYSQL_ROOT_PASSWORD={root_password}",
        "-e",
        f"MYSQL_DATABASE={database}",
        "-p",
        "0:3306",
        image,
        *(server_args if server_args is not None else _mysql_server_command_args(image)),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)  # noqa: S603
    port_line = (
        subprocess.check_output(  # noqa: S603
            [docker, "port", container_name, "3306/tcp"], text=True
        )
        .strip()
        .splitlines()[0]
    )
    return int(port_line.rsplit(":", maxsplit=1)[-1])


def _wait_for_mysql_ready(container_name: str, *, root_password: str, timeout_s: float = 90.0) -> None:
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError("Docker is unavailable")
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        proc = subprocess.run(  # noqa: S603
            [
                docker,
                "exec",
                container_name,
                "mysqladmin",
                "ping",
                "-uroot",
                f"-p{root_password}",
                "-h",
                "127.0.0.1",
                "--protocol=tcp",
                "--silent",
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        if proc.returncode == 0:
            return
        time.sleep(0.5)

    logs = ""
    try:
        logs = subprocess.check_output(  # noqa: S603
            [docker, "logs", "--tail", "40", container_name],
            text=True,
            stderr=subprocess.STDOUT,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        logs = f"<failed to read logs: {exc}>"
    raise RuntimeError(f"MySQL still not ready (timeout)\n--- docker logs ---\n{logs}")


def _docker_drop_database(container_name: str, *, root_password: str, database: str) -> None:
    docker = shutil.which("docker")
    if docker is None:
        return
    subprocess.run(  # noqa: S603
        [
            docker,
            "exec",
            container_name,
            "mysql",
            "-uroot",
            f"-p{root_password}",
            "-e",
            f"DROP DATABASE IF EXISTS `{database}`;",
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )


def _start_mysql_endpoint(
    image: str,
    *,
    container_name: str | None = None,
    root_password: str | None = None,
) -> Generator[_MySQLEndpoint, None, None]:
    """启动指定镜像的 MySQL 容器并 yield endpoint, 结束后清理."""
    _docker_pull_if_needed(image)
    if not _docker_image_exists(image):
        pytest.skip(f"MySQL image not available: {image} (set LUSH_TEST_MYSQL_PULL=1 to pull)")

    name = container_name or f"lush-sqlalchemyx-mysql-pytest-{uuid.uuid4().hex[:10]}"
    password = root_password or uuid.uuid4().hex
    database = f"lush_test_{uuid.uuid4().hex[:12]}"

    port = _docker_start_mysql(name, image=image, root_password=password, database=database)
    try:
        _wait_for_mysql_ready(name, root_password=password, timeout_s=90.0)
        ep = _MySQLEndpoint(
            host="127.0.0.1",
            port=port,
            user="root",
            password=password,
            database=database,
            container_name=name,
            image=image,
        )
        _validate_test_endpoint(ep)
        yield ep
    finally:
        _docker_drop_database(name, root_password=password, database=database)
        _docker_rm_if_exists(name)


@pytest.fixture(scope="session")
def mysql_endpoint() -> Generator[_MySQLEndpoint, None, None]:
    if not _docker_available():
        raise RuntimeError("Docker is unavailable. Enable Docker to run MySQL-backed tests.")
    yield from _start_mysql_endpoint(
        os.getenv("LUSH_TEST_MYSQL_IMAGE") or _choose_mysql_image(),
        container_name=os.getenv("LUSH_TEST_MYSQL_CONTAINER"),
        root_password=os.getenv("LUSH_TEST_MYSQL_ROOT_PASSWORD"),
    )


@pytest.fixture(scope="session")
def mysql57_endpoint() -> Generator[_MySQLEndpoint, None, None]:
    if not _docker_available():
        pytest.skip("Docker unavailable")
    yield from _start_mysql_endpoint(_mysql57_image())


@pytest.fixture(scope="session")
def mysql8_endpoint() -> Generator[_MySQLEndpoint, None, None]:
    if not _docker_available():
        pytest.skip("Docker unavailable")
    yield from _start_mysql_endpoint(_mysql8_image())
