"""Shared pytest fixtures, including a real throwaway PostgreSQL server."""

from __future__ import annotations

import shutil
import socket
import subprocess  # nosec B404 - test harness runs the local postgres binaries
import tempfile
import threading
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from taskboard11_api.main import app


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
    return port


def _run(*args: str) -> None:
    subprocess.run(args, check=True, capture_output=True, text=True)  # nosec B603


class PgServer:
    """A local PostgreSQL server in a temporary directory (trust auth, TCP only)."""

    def __init__(self, root: Path) -> None:
        for binary in ("initdb", "pg_ctl", "createdb"):
            if shutil.which(binary) is None:
                raise RuntimeError(f"{binary} not found on PATH: run inside devbox (devbox run)")
        self.data = root / "data"
        self.log = root / "postgres.log"
        self.port = _free_port()
        _run("initdb", "-A", "trust", "-U", "postgres", "-D", str(self.data))
        self.start()
        self._createdb("taskboard_test")

    def _createdb(self, name: str) -> None:
        _run("createdb", "-h", "127.0.0.1", "-p", str(self.port), "-U", "postgres", name)

    def _url(self, database: str) -> str:
        return f"postgresql://postgres@127.0.0.1:{self.port}/{database}"

    @property
    def url(self) -> str:
        return self._url("taskboard_test")

    def is_running(self) -> bool:
        r = subprocess.run(  # nosec B603 B607
            ["pg_ctl", "status", "-D", str(self.data)], capture_output=True, text=True
        )
        return r.returncode == 0

    def start(self) -> None:
        opts = f"-p {self.port} -c listen_addresses=127.0.0.1 -c unix_socket_directories=''"
        _run("pg_ctl", "start", "-w", "-D", str(self.data), "-l", str(self.log), "-o", opts)

    def stop(self) -> None:
        _run("pg_ctl", "stop", "-m", "fast", "-w", "-D", str(self.data))

    def ensure_running(self) -> None:
        if not self.is_running():
            self.start()

    def create_database(self) -> str:
        """Create a new, empty, uniquely named database and return its URL."""
        self.ensure_running()
        name = f"t_{uuid.uuid4().hex[:12]}"
        self._createdb(name)
        return self._url(name)


@pytest.fixture(scope="session")
def pg_server() -> Iterator[PgServer]:
    with tempfile.TemporaryDirectory(prefix="taskboard-pg-") as tmp:
        server = PgServer(Path(tmp))
        try:
            yield server
        finally:
            if server.is_running():
                server.stop()


@pytest.fixture(scope="session", autouse=True)
def _database_env(pg_server: PgServer) -> Iterator[None]:
    mp = pytest.MonkeyPatch()
    mp.setenv("DATABASE_URL", pg_server.url)
    try:
        yield
    finally:
        mp.undo()


@pytest.fixture(autouse=True)
def clean_tasks(pg_server: PgServer) -> None:
    """Start every test with an empty tasks table (when the table and psycopg exist)."""
    pg_server.ensure_running()
    try:
        import psycopg
    except ImportError:
        return  # psycopg is added with the implementation; nothing to truncate yet
    with psycopg.connect(pg_server.url, autocommit=True) as conn:
        exists = conn.execute("SELECT to_regclass('public.tasks')").fetchone()
        if exists and exists[0] is not None:
            conn.execute("TRUNCATE tasks RESTART IDENTITY")


@pytest.fixture()
def unreachable_database_url() -> str:
    """A URL to 127.0.0.1 on a port where nothing listens."""
    return f"postgresql://postgres@127.0.0.1:{_free_port()}/taskboard_test"


@pytest.fixture()
def hanging_database_url() -> Iterator[str]:
    """A URL to a local socket that accepts connections and never answers."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(16)
    port = server.getsockname()[1]
    held: list[socket.socket] = []
    stop = threading.Event()

    def accept_loop() -> None:
        server.settimeout(0.2)
        while not stop.is_set():
            try:
                conn, _ = server.accept()
            except OSError:
                continue
            held.append(conn)

    thread = threading.Thread(target=accept_loop, daemon=True)
    thread.start()
    try:
        yield f"postgresql://postgres@127.0.0.1:{port}/taskboard_test"
    finally:
        stop.set()
        thread.join(timeout=2)
        for c in held:
            c.close()
        server.close()


@pytest.fixture()
def client() -> TestClient:
    """A TestClient for the FastAPI application."""
    return TestClient(app)
