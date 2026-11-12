"""FastAPI entry point for taskboard11-api."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel

from . import __version__, tasks
from .db import Database, DatabaseUnavailableError
from .logging_config import configure_logging
from .metrics import MetricsMiddleware
from .tasks.store import TaskStore
from .tracing import configure_tracing, tracing_enabled

configure_logging(level=os.environ.get("LOG_LEVEL", "INFO"))
if tracing_enabled():
    configure_tracing()


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Install a fresh database and task store on every startup.

    Tries to create the schema once; an unreachable database never fails
    startup (the schema is then created lazily on the first successful connect).
    """
    database = Database()
    application.state.database = database
    application.state.task_store = TaskStore(database)
    try:
        database.ensure_schema()
    except DatabaseUnavailableError:
        logger.warning("database_unavailable_at_startup")
    yield


logger = structlog.get_logger()

app = FastAPI(title="taskboard11-api", version=__version__, lifespan=lifespan)
app.state.database = Database()
app.state.task_store = TaskStore(app.state.database)
app.include_router(tasks.router)
app.add_middleware(MetricsMiddleware)
if tracing_enabled():
    FastAPIInstrumentor.instrument_app(app)


class HealthResponse(BaseModel):
    status: str


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness probe — returns 200 as long as the process is responding."""
    return HealthResponse(status="ok")


@app.get("/ready", response_model=HealthResponse)
def ready(request: Request) -> Response:
    """Readiness probe — 200 when the database answers, else 503."""
    if request.app.state.database.is_ready():
        return JSONResponse(status_code=200, content={"status": "ready"})
    return JSONResponse(status_code=503, content={"status": "unavailable"})


@app.get("/ping")
def ping() -> dict[str, str]:
    """Simple ping endpoint."""
    return {"pong": "taskboard11-api"}


@app.get("/metrics")
def metrics() -> Response:
    """Prometheus scrape endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
