"""PostgreSQL access: connections with timeouts, schema bootstrap and readiness."""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
import structlog

logger = structlog.get_logger(__name__)

_SCHEMA_LOCK_KEY = 2002

_CREATE_TASKS = """
CREATE TABLE IF NOT EXISTS tasks (
    seq        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id         uuid        NOT NULL UNIQUE,
    title      text        NOT NULL,
    due_date   date        NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
"""


class DatabaseUnavailableError(Exception):
    """The database cannot be reached or did not answer in time."""


class Database:
    """Opens short-lived connections and makes sure the schema exists."""

    def __init__(self, url: str | None = None) -> None:
        self._url = url
        self._ready_urls: set[str] = set()
        self._lock = threading.Lock()

    def _resolve_url(self) -> str:
        url = self._url or os.environ.get("DATABASE_URL")
        if not url:
            logger.warning("database_unavailable", error_type="MissingDatabaseUrl")
            raise DatabaseUnavailableError("DATABASE_URL is not set")
        return url

    @staticmethod
    def _connect(url: str) -> psycopg.Connection[Any]:
        return psycopg.connect(
            url,
            connect_timeout=3,
            options="-c statement_timeout=3000",
            tcp_user_timeout=3000,
        )

    def _ensure_schema(self, url: str) -> None:
        with self._lock:
            if url in self._ready_urls:
                return
            with self._connect(url) as conn:
                with conn.transaction():
                    conn.execute("SELECT pg_advisory_xact_lock(%s)", (_SCHEMA_LOCK_KEY,))
                    conn.execute(_CREATE_TASKS)
            self._ready_urls.add(url)
            logger.info("schema_ready")

    def ensure_schema(self) -> None:
        """Create the schema if missing (idempotent)."""
        url = self._resolve_url()
        try:
            self._ensure_schema(url)
        except (psycopg.OperationalError, psycopg.InterfaceError) as exc:
            logger.warning("database_unavailable", error_type=type(exc).__name__)
            raise DatabaseUnavailableError("database unavailable") from exc

    @contextmanager
    def connection(self) -> Iterator[psycopg.Connection[Any]]:
        """Yield a connection; commit on success, roll back on error, always close."""
        url = self._resolve_url()
        try:
            self._ensure_schema(url)
            conn = self._connect(url)
        except (psycopg.OperationalError, psycopg.InterfaceError) as exc:
            logger.warning("database_unavailable", error_type=type(exc).__name__)
            raise DatabaseUnavailableError("database unavailable") from exc
        try:
            try:
                yield conn
                conn.commit()
            except BaseException:
                try:
                    conn.rollback()
                except psycopg.Error:
                    pass
                raise
        except (psycopg.OperationalError, psycopg.InterfaceError) as exc:
            logger.warning("database_unavailable", error_type=type(exc).__name__)
            raise DatabaseUnavailableError("database unavailable") from exc
        finally:
            try:
                conn.close()
            except psycopg.Error:
                pass

    def is_ready(self) -> bool:
        """True when the database answers; never raises."""
        try:
            with self.connection() as conn:
                conn.execute("SELECT 1")
        except (psycopg.Error, DatabaseUnavailableError):
            return False
        return True
