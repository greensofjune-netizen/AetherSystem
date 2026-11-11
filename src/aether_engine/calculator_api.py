"""Stateless, bearer-token-protected API for the public calculator subset."""

from __future__ import annotations

import hmac
import os
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from .engine_runtime import EngineConfig, EngineRuntime
from .formula_routes import formula_engine, formula_router
from .request_telemetry import install_request_telemetry

MAX_REQUEST_BYTES = 64_000
SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}


def create_app(token: str | None = None) -> FastAPI:
    """Create the hosted calculator API; loopback never bypasses authentication."""
    app = FastAPI(
        title="Aether Calculator API",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    runtime = EngineRuntime(formula_engine, config=EngineConfig.from_environment())
    runtime.start()
    app.state.engine_runtime = runtime

    @app.middleware("http")
    async def require_origin_token(request: Request, call_next: Any) -> Response:
        if request.url.path == "/health" and request.method in {"GET", "HEAD"}:
            response = await call_next(request)
        else:
            expected_token = (
                token
                if token is not None
                else os.environ.get("AETHER_CALCULATOR_TOKEN", "")
            )
            if not expected_token:
                return JSONResponse(
                    {"detail": "Calculator API authentication is not configured."},
                    status_code=503,
                    headers=SECURITY_HEADERS,
                )
            scheme, separator, supplied_token = request.headers.get(
                "authorization", ""
            ).partition(" ")
            if (
                not separator
                or scheme.casefold() != "bearer"
                or not hmac.compare_digest(
                    supplied_token.encode("utf-8"),
                    expected_token.encode("utf-8"),
                )
            ):
                return JSONResponse(
                    {"detail": "A valid bearer token is required."},
                    status_code=401,
                    headers={**SECURITY_HEADERS, "WWW-Authenticate": "Bearer"},
                )
            if request.method == "POST":
                if (
                    request.headers.get("content-type", "").split(";")[0]
                    != "application/json"
                ):
                    return JSONResponse(
                        {"detail": "JSON requests required."},
                        status_code=415,
                        headers=SECURITY_HEADERS,
                    )
                body = bytearray()
                async for chunk in request.stream():
                    body.extend(chunk)
                    if len(body) > MAX_REQUEST_BYTES:
                        return JSONResponse(
                            {"detail": "Request exceeds the 64 KB limit."},
                            status_code=413,
                            headers=SECURITY_HEADERS,
                        )
                request._body = bytes(body)
            response = await call_next(request)

        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response

    install_request_telemetry(app, "calculator-api")
    app.router.add_event_handler("shutdown", runtime.stop)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "healthy", "application": "Aether Calculator API"}

    @app.get("/api/engine/status")
    def engine_status(request: Request) -> dict[str, Any]:
        return request.app.state.engine_runtime.status()

    app.include_router(formula_router)
    return app


app = create_app()
