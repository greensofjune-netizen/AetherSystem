from __future__ import annotations

import json
import logging
from time import perf_counter
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import Response

LOGGER = logging.getLogger("aether_engine.requests")


def install_request_telemetry(app: FastAPI, component: str) -> None:
    @app.middleware("http")
    async def request_telemetry(request: Request, call_next: Any) -> Response:
        request_id = uuid4().hex
        request.state.request_id = request_id
        started = perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            LOGGER.info(
                json.dumps(
                    {
                        "event": "request.completed",
                        "request_id": request_id,
                        "component": component,
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": status_code,
                        "duration_ms": round((perf_counter() - started) * 1000, 2),
                    },
                    separators=(",", ":"),
                )
            )
