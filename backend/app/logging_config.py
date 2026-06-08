"""
Structured JSON Logging
────────────────────────
Configures the application logger to emit structured JSON records with:
  - request_id (per-request UUID injected via middleware)
  - benchmark_id / experiment_id (when available in context)
  - event name, timestamp, duration_ms, level

Usage:
    from app.logging_config import configure_logging, get_logger

    configure_logging()
    log = get_logger(__name__)
    log.info("benchmark_started", extra={"benchmark_id": run.id, "workload": "image_processing"})

Middleware integration (see app/main.py):
    app.add_middleware(RequestIDMiddleware)

JSON log record format:
    {
      "timestamp": "2026-06-05T12:00:00.123456Z",
      "level": "INFO",
      "logger": "app.services.benchmark_service",
      "event": "benchmark_started",
      "request_id": "abc-123",
      "benchmark_id": "def-456",
      "duration_ms": 142.3
    }
"""
from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

# ── Context variables ─────────────────────────────────────────────────────────
# These survive async context switches and thread boundaries within a request.

request_id_var: ContextVar[str] = ContextVar("request_id", default="")
benchmark_id_var: ContextVar[str] = ContextVar("benchmark_id", default="")
experiment_id_var: ContextVar[str] = ContextVar("experiment_id", default="")


# ── JSON log formatter ─────────────────────────────────────────────────────────

class JSONFormatter(logging.Formatter):
    """
    Formats log records as single-line JSON objects.
    Extra fields passed via `extra={}` are merged into the top-level record.
    """

    def format(self, record: logging.LogRecord) -> str:
        # Base fields present in every record
        log_dict: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }

        # Context variables — injected by middleware / service layer
        if rid := request_id_var.get(""):
            log_dict["request_id"] = rid
        if bid := benchmark_id_var.get(""):
            log_dict["benchmark_id"] = bid
        if eid := experiment_id_var.get(""):
            log_dict["experiment_id"] = eid

        # Extra fields from log call: log.info("msg", extra={"duration_ms": 42})
        for key in ("benchmark_id", "experiment_id", "duration_ms",
                    "workload_type", "worker_count", "input_size",
                    "speedup", "status", "node_id", "hostname"):
            val = getattr(record, key, None)
            if val is not None:
                log_dict[key] = val

        # Exception info
        if record.exc_info:
            log_dict["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_dict, default=str)


# ── Human-readable formatter (dev) ────────────────────────────────────────────

class DevFormatter(logging.Formatter):
    """
    Compact human-readable format for local development.
    Includes request_id and extra fields inline.
    """

    FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = {}
        if rid := request_id_var.get(""):
            extras["req"] = rid[:8]
        if bid := benchmark_id_var.get(""):
            extras["bm"] = bid[:8]
        for key in ("duration_ms", "workload_type", "status"):
            val = getattr(record, key, None)
            if val is not None:
                extras[key] = val
        if extras:
            kv = " ".join(f"{k}={v}" for k, v in extras.items())
            return f"{base} [{kv}]"
        return base

    def formatTime(self, record: logging.LogRecord, datefmt=None) -> str:
        return datetime.fromtimestamp(record.created).strftime("%H:%M:%S.%f")[:-3]


# ── Configuration ─────────────────────────────────────────────────────────────

def configure_logging(
    level: str = "INFO",
    json_logs: bool = False,
) -> None:
    """
    Configure root logger.

    Args:
        level: Logging level string ("DEBUG", "INFO", "WARNING", "ERROR").
        json_logs: If True, emit JSON (production). If False, human-readable (dev).
    """
    formatter = JSONFormatter() if json_logs else DevFormatter(fmt=DevFormatter.FMT)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Suppress noisy third-party loggers
    for noisy in ("uvicorn.access", "sqlalchemy.engine", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Convenience wrapper for module-level logger acquisition."""
    return logging.getLogger(name)


# ── Request ID middleware ─────────────────────────────────────────────────────

class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Assigns a unique UUID to every incoming HTTP request.
    The ID is:
      1. Read from X-Request-ID header if present (for tracing across services).
      2. Otherwise generated fresh.
      3. Stored in request_id_var context variable (available in all log records).
      4. Returned in X-Request-ID response header.
    """

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = request_id_var.set(request_id)
        try:
            t0 = time.perf_counter()
            response = await call_next(request)
            duration_ms = (time.perf_counter() - t0) * 1000

            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time-Ms"] = str(round(duration_ms, 2))

            logging.getLogger("app.http").info(
                "%s %s %d",
                request.method,
                request.url.path,
                response.status_code,
                extra={"duration_ms": round(duration_ms, 2)},
            )
            return response
        finally:
            request_id_var.reset(token)


# ── Benchmark timing context manager ──────────────────────────────────────────

class BenchmarkTimer:
    """
    Context manager that logs structured timing events for a benchmark run.

    Usage:
        with BenchmarkTimer(run_id, workload_type):
            result = workload.run(...)
    """

    def __init__(self, run_id: str, workload_type: str):
        self.run_id = run_id
        self.workload_type = workload_type
        self._token = None
        self._t0: float = 0

    def __enter__(self):
        self._token = benchmark_id_var.set(self.run_id)
        self._t0 = time.perf_counter()
        logging.getLogger("app.benchmark").info(
            "benchmark_started",
            extra={
                "benchmark_id": self.run_id,
                "workload_type": self.workload_type,
            },
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.perf_counter() - self._t0) * 1000
        status = "failed" if exc_type else "completed"
        logging.getLogger("app.benchmark").info(
            "benchmark_%s" % status,
            extra={
                "benchmark_id": self.run_id,
                "workload_type": self.workload_type,
                "duration_ms": round(duration_ms, 2),
                "status": status,
            },
        )
        if self._token:
            benchmark_id_var.reset(self._token)
        return False   # don't suppress exceptions
