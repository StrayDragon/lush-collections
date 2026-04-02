"""Shared pytest fixtures for integration-ish tests.

Goals:
- Automatically provision external dependencies (e.g. MySQL) via Docker.
- Prefer using existing local Docker images to avoid pulling (fast path).
- Idempotent: cleanup containers and drop random test databases on teardown.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import uuid
from collections.abc import Generator
from dataclasses import dataclass

import pytest


@dataclass(frozen=True, slots=True)
class _MySQLEndpoint:
    host: str
    port: int
    user: str
    password: str
    database: str
    container_name: str | None = None

    @property
    def sqlalchemy_url(self) -> str:
        # NOTE: driver is a dev dependency used only in tests.
        return f"mysql+aiomysql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


def _docker_available() -> bool:
    docker = shutil.which("docker")
    if docker is None:
        return False
    try:
        proc = subprocess.run(  # noqa: S603
            [docker, "ps"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except OSError:
        return False
    else:
        return proc.returncode == 0


def _docker_image_exists(image: str) -> bool:
    docker = shutil.which("docker")
    if docker is None:
        return False
    try:
        proc = subprocess.run(  # noqa: S603
            [docker, "image", "inspect", image],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except OSError:
        return False
    else:
        return proc.returncode == 0


def _choose_mysql_image() -> str:
    env_image = os.getenv("LUSH_TEST_MYSQL_IMAGE")
    if env_image:
        return env_image

    # Prefer local images to avoid pulling (fast path)
    candidates = [
        "mysql:5.7",
        "mysql:5.7.42-debian",
        # MySQL 8.4 removed mysql_native_password plugin by default, and requires
        # caching_sha2_password support on the client side. Prefer 5.7 for
        # deterministic tests unless user overrides `LUSH_TEST_MYSQL_IMAGE`.
        "mysql:8.0.40-debian",
        "mysql:8.0",
        "mysql:8",
        "mysql:8.4",
    ]
    for image in candidates:
        if _docker_image_exists(image):
            return image

    # Fallback: docker will pull if missing
    return "mysql:8"


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


def _docker_start_mysql(container_name: str, *, image: str, root_password: str, database: str) -> int:
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError("Docker is unavailable")
    _docker_rm_if_exists(container_name)
    subprocess.run(  # noqa: S603
        [
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
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )

    port_line = subprocess.check_output([docker, "port", container_name, "3306/tcp"], text=True).strip().splitlines()[0]  # noqa: S603
    return int(port_line.rsplit(":", maxsplit=1)[-1])


def _wait_for_mysql_ready(container_name: str, *, root_password: str, timeout_s: float = 45.0) -> None:
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError("Docker is unavailable")
    deadline = time.time() + timeout_s
    while True:
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

        if time.time() >= deadline:
            raise RuntimeError("MySQL still not ready (timeout)")
        time.sleep(0.5)


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


@pytest.fixture(scope="session")
def mysql_endpoint() -> Generator[_MySQLEndpoint, None, None]:
    if not _docker_available():
        raise RuntimeError("Docker is unavailable. Enable Docker to run MySQL-backed tests.")

    image = _choose_mysql_image()
    container_name = os.getenv("LUSH_TEST_MYSQL_CONTAINER", f"lush-sqlalchemyx-mysql-pytest-{uuid.uuid4().hex[:10]}")
    root_password = os.getenv("LUSH_TEST_MYSQL_ROOT_PASSWORD", uuid.uuid4().hex)
    database = f"lush_test_{uuid.uuid4().hex[:12]}"

    port = _docker_start_mysql(container_name, image=image, root_password=root_password, database=database)
    try:
        _wait_for_mysql_ready(container_name, root_password=root_password, timeout_s=45.0)
        yield _MySQLEndpoint(
            host="127.0.0.1",
            port=port,
            user="root",
            password=root_password,
            database=database,
            container_name=container_name,
        )
    finally:
        _docker_drop_database(container_name, root_password=root_password, database=database)
        _docker_rm_if_exists(container_name)
