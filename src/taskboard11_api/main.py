"""FastAPI entry point for taskboard11-api."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel

from . import __version__, tasks
from .logging_config import configure_logging
from .metrics import MetricsMiddleware
from .tasks.store import TaskStore
from .tracing import configure_tracing, tracing_enabled

configure_logging(level=os.environ.get("LOG_LEVEL", "INFO"))
if tracing_enabled():
    configure_tracing()


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Install a fresh, empty task store on every startup."""
    application.state.task_store = TaskStore()
    yield


app = FastAPI(title="taskboard11-api", version=__version__, lifespan=lifespan)
app.state.task_store = TaskStore()
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
def ready() -> HealthResponse:
    """Readiness probe — returns 200 when the service is ready to accept traffic."""
    return HealthResponse(status="ready")


@app.get("/ping")
def ping() -> dict[str, str]:
    """Simple ping endpoint."""
    return {"pong": "taskboard11-api"}


@app.get("/metrics")
def metrics() -> Response:
    """Prometheus scrape endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
