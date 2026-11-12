from __future__ import annotations

import asyncio
import hmac
import ipaddress
import json
import logging
import math
import os
import sqlite3
import sys
import time
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, Thread
from typing import Annotated, Any, Literal, NoReturn

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from . import live_sync_supervisor
from .ai_bridge import LocalAirGappedEngine
from .astrology import NatalChartRequest, calculate_natal_chart
from .astronomy_engine import get_astronomy_engine
from .backups import DEFAULT_BACKUP_RETENTION, write_backup
from .database import AetherStore, Event, TaskConflictError
from .engine_core import EngineOrchestrator
from .engine_doctor import AetherEngineDoctor
from .engine_runtime import EngineConfig, EngineNotReadyError, EngineRuntime
from .historian import CoPilotHistorian
from .inference_scheduler import (
    InferenceCapacityError,
    InferenceQueueTimeoutError,
    InferenceSchedulerClosedError,
)
from .local_ai_runtime import (
    DEFAULT_LOCAL_MODEL,
    LocalModelUnavailableError,
)
from .model_providers import (
    ChatRequest,
    LocalEngineProvider,
    LocalInferenceProviderError,
    OllamaProvider,
    OllamaProviderError,
    ProviderMessage,
)
from .multimodal import ImageAttachment, validate_image_batch
from .propulsion_matrix import KineticPropulsionArchive
from .request_telemetry import install_request_telemetry
from .scheduler import (
    SchedulerError,
    backup_schedule_status,
    install_backup_schedule,
    uninstall_backup_schedule,
)

ReasoningEffort = Literal["none", "low", "medium", "high", "xhigh", "max"]
TaskPriority = Literal["low", "normal", "high"]
TaskStatus = Literal["pending", "done"]
SourceLanguage = Literal["python", "js", "cpp", "rust", "go", "swift", "shell"]
NodeName = Literal["COPERNICUS", "HISTORIAN", "MATRIX", "ATLAS"]
UNIFIED_DISPATCH_TOPIC = "unified-dispatch"
UNIFIED_PAYLOAD_LIMIT_BYTES = 32_768
UNIFIED_EVENT_REPLAY_LIMIT = 500
UNIFIED_DISPATCH_RATE_LIMIT = 120
UNIFIED_DISPATCH_RATE_WINDOW_SECONDS = 60.0


class UnifiedDispatchBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or scope["path"] != "/api/v1/unified/dispatch"
        ):
            await self.app(scope, receive, send)
            return

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > self.max_bytes:
                response = JSONResponse(
                    status_code=413,
                    content={
                        "detail": (
                            "Request body must be no larger than "
                            f"{self.max_bytes} bytes."
                        )
                    },
                )
                await response(scope, receive, send)
                return
            body.extend(chunk)
            if not message.get("more_body", False):
                break

        replayed = False

        async def replay_receive() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay_receive, send)


app = FastAPI(
    title="Aether Engine API",
    description=(
        "Local REST API; non-loopback clients require the AETHER_API_TOKEN secret."
    ),
    version="1.0.0",
)
app.state.local_model_status = {"model": DEFAULT_LOCAL_MODEL, "status": "pending"}
app.add_middleware(
    UnifiedDispatchBodyLimitMiddleware,
    max_bytes=UNIFIED_PAYLOAD_LIMIT_BYTES,
)

allowed_origins = [
    origin.strip()
    for origin in os.environ.get("AETHER_CORS_ORIGINS", "").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Last-Event-ID", "X-Aether-Token"],
)

engine = LocalAirGappedEngine()
engine_config = EngineConfig.from_environment()
engine_runtime = EngineRuntime(
    EngineOrchestrator(),
    providers={
        "local": LocalEngineProvider(lambda: engine),
        "ollama": OllamaProvider(
            timeout=engine_config.model_request_timeout_seconds,
            preload_timeout=engine_config.model_preload_timeout_seconds,
        ),
    },
    config=engine_config,
)
engine_runtime.start()
app.state.engine_runtime = engine_runtime
app.router.add_event_handler("shutdown", engine_runtime.stop)
dispatch_rate_lock = Lock()
unified_dispatch_lock = asyncio.Lock()
dispatch_attempts: dict[str, deque[float]] = {}

SOURCE_CLIENT_PATH = Path(__file__).resolve().parents[2] / "frontend" / "aether_client.js"
INSTALLED_CLIENT_PATH = (
    Path(sys.prefix) / "share" / "aether-engine" / "frontend" / "aether_client.js"
)
SOURCE_MONITOR_PATH = SOURCE_CLIENT_PATH.with_name("index.html")
INSTALLED_MONITOR_PATH = INSTALLED_CLIENT_PATH.with_name("index.html")
SOURCE_TASKS_PATH = SOURCE_CLIENT_PATH.with_name("monitor_tasks.js")
INSTALLED_TASKS_PATH = INSTALLED_CLIENT_PATH.with_name("monitor_tasks.js")


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChatCompletionRequest(StrictRequest):
    prompt: str = Field(min_length=1, max_length=32_768)
    reasoning_effort: ReasoningEffort = "medium"
    images: list[ImageAttachment] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def validate_images(self) -> ChatCompletionRequest:
        validate_image_batch(self.images)
        return self


class ChatCompletionResponse(BaseModel):
    model: str
    response: str
    status: str
    tokens_used: int | None = None


class EventCreate(StrictRequest):
    topic: str = Field(default="general", max_length=300)
    message: str = Field(min_length=1, max_length=8_000)


class TaskCreate(StrictRequest):
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=8_000)
    priority: TaskPriority = "normal"
    due_date: str | None = None


class TaskUpdate(StrictRequest):
    title: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=8_000)
    priority: TaskPriority | None = None
    due_date: str | None = None
    clear_due_date: bool = False
    expected_values: dict[str, str | None] | None = Field(default=None, max_length=4)


class RestoreRequest(StrictRequest):
    backup: dict[str, Any]
    replace: bool = False


class BackupRequest(StrictRequest):
    keep: int = Field(default=DEFAULT_BACKUP_RETENTION, ge=1, le=10_000)


class UnifiedEnvelope(StrictRequest):
    protocol_version: Literal["1.0.0"]
    source_lang: SourceLanguage
    node: NodeName
    event: str = Field(min_length=1, max_length=64, pattern=r"^[A-Z][A-Z0-9_]*$")
    timestamp: float = Field(strict=True, ge=0, allow_inf_nan=False)
    payload: dict[str, Any] = Field(max_length=64)

    @model_validator(mode="after")
    def enforce_payload_size(self) -> UnifiedEnvelope:
        if len(self.model_dump_json().encode("utf-8")) > UNIFIED_PAYLOAD_LIMIT_BYTES:
            raise ValueError(
                f"Envelope must be no larger than {UNIFIED_PAYLOAD_LIMIT_BYTES} bytes."
            )
        return self


class UnifiedDispatchResponse(BaseModel):
    status: Literal["ACCEPTED"]
    persisted: bool
    event_id: int
    live_subscribers_notified: int


def get_database_path() -> Path:
    configured_path = os.environ.get("AETHER_DATABASE_PATH")
    if configured_path is not None:
        if not configured_path.strip():
            raise ValueError("AETHER_DATABASE_PATH cannot be empty.")
        return Path(configured_path).expanduser()

    directory = Path.cwd().resolve()
    project_root = next(
        (
            parent
            for parent in (directory, *directory.parents)
            if (parent / "pyproject.toml").is_file()
        ),
        directory,
    )
    return project_root / ".aether-engine.sqlite3"


def get_store() -> AetherStore:
    return AetherStore(get_database_path())


def _raise_bad_request(error: ValueError) -> NoReturn:
    raise HTTPException(status_code=422, detail=str(error)) from error


def _check_unified_dispatch_rate(client_host: str) -> None:
    now = time.monotonic()
    with dispatch_rate_lock:
        for host, history in tuple(dispatch_attempts.items()):
            while (
                history
                and now - history[0] >= UNIFIED_DISPATCH_RATE_WINDOW_SECONDS
            ):
                history.popleft()
            if not history:
                del dispatch_attempts[host]
        attempts = dispatch_attempts.setdefault(client_host, deque())
        if len(attempts) >= UNIFIED_DISPATCH_RATE_LIMIT:
            retry_after = max(
                1,
                math.ceil(
                    UNIFIED_DISPATCH_RATE_WINDOW_SECONDS - (now - attempts[0])
                ),
            )
            raise HTTPException(
                status_code=429,
                detail="Unified dispatch rate limit exceeded.",
                headers={"Retry-After": str(retry_after)},
            )
        attempts.append(now)


def _list_unified_dispatch_events(
    limit: int = UNIFIED_EVENT_REPLAY_LIMIT,
) -> list[Event]:
    return CoPilotHistorian(get_store()).history(
        limit=limit, topic=UNIFIED_DISPATCH_TOPIC
    )


def _record_unified_dispatch_event(envelope: dict[str, Any]) -> Event:
    return CoPilotHistorian(get_store()).record(
        UNIFIED_DISPATCH_TOPIC,
        json.dumps(envelope, ensure_ascii=False, separators=(",", ":")),
    )


def _dispatch_event_record(event: Event) -> dict[str, Any]:
    return {
        "event_id": event.id,
        "created_at": event.created_at,
        "envelope": json.loads(event.message),
    }


def _format_sse(event_name: str, record: dict[str, Any], event_id: int | None) -> str:
    identifier = f"id: {event_id}\n" if event_id is not None else ""
    data = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    return f"{identifier}event: {event_name}\ndata: {data}\n\n"


def _start_local_model_preload() -> None:
    app.state.local_model_status = {
        "model": DEFAULT_LOCAL_MODEL,
        "status": "loading",
    }

    def preload() -> None:
        try:
            engine_runtime.preload("ollama", DEFAULT_LOCAL_MODEL)
        except LocalModelUnavailableError as error:
            logging.getLogger(__name__).warning(
                "Default local model could not be preloaded: %s", error
            )
            app.state.local_model_status = {
                "model": DEFAULT_LOCAL_MODEL,
                "status": "unavailable",
                "detail": str(error),
            }
        else:
            app.state.local_model_status = {
                "model": DEFAULT_LOCAL_MODEL,
                "status": "ready",
            }

    Thread(target=preload, name="aether-model-preload", daemon=True).start()


app.router.add_event_handler("startup", _start_local_model_preload)


@app.middleware("http")
async def authorize_remote_clients(request: Request, call_next: Any) -> Any:
    """Require a shared secret for every non-loopback HTTP request."""
    if request.method == "OPTIONS":
        return await call_next(request)
    try:
        authorize_aether_client(request)
    except HTTPException as error:
        return JSONResponse(
            status_code=error.status_code,
            content={"detail": error.detail},
            headers=error.headers,
        )
    return await call_next(request)


install_request_telemetry(app, "aether-api")


def authorize_aether_client(request: Request) -> None:
    """Allow loopback clients and authenticate all other peers by shared token."""
    client = request.client
    try:
        address = ipaddress.ip_address(client.host) if client is not None else None
    except ValueError:
        address = None
    if address is not None and address.is_loopback:
        return

    expected_token = os.environ.get("AETHER_API_TOKEN", "")
    provided_token = request.headers.get("X-Aether-Token", "")
    if not expected_token or not hmac.compare_digest(
        provided_token.encode("utf-8"), expected_token.encode("utf-8")
    ):
        raise HTTPException(
            status_code=401,
            detail=(
                "Unauthorized: Valid X-Aether-Token header required for remote access."
            ),
        )


@app.get("/health")
def health_check() -> dict[str, str | bool]:
    """Report server health and whether the configured model file is present."""
    return {
        "status": "healthy",
        "model": engine.model_path.name,
        "model_available": engine.model_path.is_file(),
    }


@app.get("/api/v1/local-model/status")
def local_model_status() -> dict[str, str]:
    return dict(app.state.local_model_status)


@app.get("/api/v1/engine/status")
def engine_status(request: Request) -> dict[str, Any]:
    return request.app.state.engine_runtime.status()


@app.get("/api/v1/propulsion/references")
def propulsion_references(q: str = Query(default="", max_length=200)) -> dict[str, Any]:
    """Search local general references with their sources and historical links."""
    try:
        archive = KineticPropulsionArchive()
        return {
            "references": archive.search_references(q),
            "lineage": archive.fetch_reference_lineage(),
        }
    except (OSError, sqlite3.Error) as error:
        logging.getLogger(__name__).exception("Propulsion archive lookup failed")
        raise HTTPException(503, "The local propulsion archive is unavailable.") from error


@app.get("/aether_client.js")
def serve_shared_javascript() -> FileResponse:
    """Serve the shared browser client."""
    for path in (SOURCE_CLIENT_PATH, INSTALLED_CLIENT_PATH):
        if path.is_file():
            return FileResponse(path, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="Shared JS file not found.")


@app.get("/monitor", include_in_schema=False)
def serve_monitor() -> FileResponse:
    for path in (SOURCE_MONITOR_PATH, INSTALLED_MONITOR_PATH):
        if path.is_file():
            return FileResponse(path, media_type="text/html")
    raise HTTPException(status_code=404, detail="Monitor page not found.")


@app.get("/monitor_tasks.js", include_in_schema=False)
def serve_monitor_tasks() -> FileResponse:
    for path in (SOURCE_TASKS_PATH, INSTALLED_TASKS_PATH):
        if path.is_file():
            return FileResponse(path, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="Monitor task script not found.")


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
def create_chat_completion(
    entry: ChatCompletionRequest,
    request: Request,
) -> ChatCompletionResponse:
    """Generate a completion using the configured local model."""
    prompt = entry.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=422, detail="Prompt cannot be blank.")

    runtime = request.app.state.engine_runtime
    try:
        if entry.images:
            result = runtime.chat(
                "ollama",
                ChatRequest(
                    model=DEFAULT_LOCAL_MODEL,
                    messages=(
                        ProviderMessage(
                            "system",
                            "Answer the user clearly and accurately. Analyze the "
                            "provided image attachments when relevant, and state "
                            "uncertainty when image details are ambiguous.",
                        ),
                        ProviderMessage(
                            "user",
                            prompt,
                            tuple(image.data for image in entry.images),
                        ),
                    ),
                    max_output_tokens=engine_config.max_output_tokens,
                ),
            )
        else:
            result = runtime.chat(
                "local",
                ChatRequest(
                    model=engine.model_path.name,
                    messages=(ProviderMessage("user", prompt),),
                    max_output_tokens=engine_config.max_output_tokens,
                    reasoning_effort=entry.reasoning_effort,
                ),
            )
    except (InferenceCapacityError, InferenceQueueTimeoutError) as error:
        raise HTTPException(
            status_code=429,
            detail=str(error),
            headers={"Retry-After": "1"},
        ) from error
    except (EngineNotReadyError, InferenceSchedulerClosedError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except LocalInferenceProviderError as error:
        detail: str | dict[str, str]
        if error.http_status == 503:
            detail = {"status": error.status, "message": str(error)}
        else:
            detail = str(error)
        raise HTTPException(status_code=error.http_status, detail=detail) from error
    except OllamaProviderError as error:
        raise HTTPException(
            status_code=503,
            detail="Local Ollama could not provide an image-aware response.",
        ) from error

    return ChatCompletionResponse(
        model=result.model,
        response=result.content,
        status="success",
    )


@app.get("/api/v1/astronomy/visible-stars")
def visible_stars(
    latitude: float = Query(default=34.0975, ge=-90, le=90),
    longitude: float = Query(default=-117.6484, ge=-180, le=180),
    max_magnitude: float = Query(default=4.0, ge=-2, le=8),
    at: datetime | None = None,
) -> dict[str, Any]:
    engine = get_astronomy_engine(latitude, longitude)
    observation_time = at or datetime.now(timezone.utc)
    if observation_time.tzinfo is None:
        observation_time = observation_time.replace(tzinfo=timezone.utc)
    else:
        observation_time = observation_time.astimezone(timezone.utc)
    try:
        stars = engine.compute_local_sky(observation_time, max_magnitude)
    except (OSError, RuntimeError, ValueError) as error:
        logging.getLogger(__name__).warning(
            "Astronomy calculation failed: %s", error
        )
        raise HTTPException(
            status_code=503,
            detail=(
                "Astronomy data could not be loaded or the requested date is "
                "unsupported."
            ),
        ) from error
    return {
        "observed_at": observation_time.isoformat(),
        "latitude": latitude,
        "longitude": longitude,
        "stars": stars,
    }


@app.get("/api/v1/tasks")
def list_tasks(
    status: TaskStatus | None = None,
    search: Annotated[str | None, Query(min_length=1, max_length=500)] = None,
) -> list[dict[str, Any]]:
    try:
        return [asdict(task) for task in get_store().list_tasks(status, search)]
    except ValueError as error:
        _raise_bad_request(error)


@app.post("/api/v1/tasks", status_code=201)
def create_task(request: TaskCreate) -> dict[str, Any]:
    try:
        task = get_store().add_task(
            request.title,
            request.description,
            request.priority,
            request.due_date,
        )
    except ValueError as error:
        _raise_bad_request(error)
    return asdict(task)


@app.patch("/api/v1/tasks/{task_id}")
def update_task(task_id: int, request: TaskUpdate) -> dict[str, Any]:
    try:
        task = get_store().update_task(
            task_id,
            title=request.title,
            description=request.description,
            priority=request.priority,
            due_date=request.due_date,
            clear_due_date=request.clear_due_date,
            expected_values=request.expected_values,
        )
    except TaskConflictError as error:
        raise HTTPException(status_code=409, detail={
            "code": "task_edit_conflict",
            "message": str(error),
            "fields": error.fields,
            "current": asdict(error.current),
        }) from error
    except ValueError as error:
        _raise_bad_request(error)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task #{task_id} was not found.")
    return asdict(task)


@app.post("/api/v1/tasks/{task_id}/complete")
def complete_task(task_id: int) -> dict[str, Any]:
    task = get_store().complete_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task #{task_id} was not found.")
    return asdict(task)


@app.post("/api/v1/tasks/{task_id}/reopen")
def reopen_task(task_id: int) -> dict[str, Any]:
    task = get_store().reopen_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task #{task_id} was not found.")
    return asdict(task)


@app.get("/api/v1/events")
def list_events(
    limit: Annotated[int, Query(ge=1, le=500)] = 20,
    search: Annotated[str | None, Query(min_length=1, max_length=500)] = None,
    topic: Annotated[str | None, Query(min_length=1, max_length=300)] = None,
    since: str | None = None,
    until: str | None = None,
) -> list[dict[str, Any]]:
    try:
        events = CoPilotHistorian(get_store()).history(
            limit, search=search, topic=topic, since=since, until=until
        )
    except ValueError as error:
        _raise_bad_request(error)
    return [asdict(event) for event in events]


@app.post("/api/v1/events", status_code=201)
def create_event(request: EventCreate) -> dict[str, Any]:
    try:
        event = CoPilotHistorian(get_store()).record(request.topic, request.message)
    except ValueError as error:
        _raise_bad_request(error)
    return asdict(event)


@app.post("/api/v1/astrology/chart")
def calculate_chart(request: NatalChartRequest) -> dict[str, object]:
    try:
        return calculate_natal_chart(request)
    except ValueError as error:
        _raise_bad_request(error)


@app.post("/api/v1/unified/dispatch")
async def unified_cross_language_dispatch(
    envelope: UnifiedEnvelope, request: Request
) -> UnifiedDispatchResponse:
    """Persist a cross-language event, update state, and notify live subscribers."""
    client_host = request.client.host if request.client is not None else ""
    _check_unified_dispatch_rate(client_host)
    envelope_data = envelope.model_dump(mode="json")
    async with unified_dispatch_lock:
        stored_event = await asyncio.to_thread(
            _record_unified_dispatch_event, envelope_data
        )
        dispatch_record = _dispatch_event_record(stored_event)
        await live_sync_supervisor.safe_update_dashboard_state(
            envelope.event,
            {
                "unified_dispatch": dispatch_record,
                "last_source_lang": envelope.source_lang,
                "last_node": envelope.node,
            },
        )
        notified = await live_sync_supervisor.supervisor.broadcast(
            event_type=envelope.event,
            data=dispatch_record,
        )
    return UnifiedDispatchResponse(
        status="ACCEPTED",
        persisted=True,
        event_id=stored_event.id,
        live_subscribers_notified=notified,
    )


@app.get("/api/v1/unified/state")
async def unified_dispatch_state() -> dict[str, Any]:
    """Return in-memory dashboard state with the durable latest dispatch."""
    state = await live_sync_supervisor.safe_get_dashboard_snapshot()
    events = await asyncio.to_thread(_list_unified_dispatch_events, 1)
    latest = _dispatch_event_record(events[0]) if events else None
    if latest is not None:
        state["unified_dispatch"] = latest
    return {"state": state, "last_dispatch": latest}


@app.get("/api/v1/unified/stream")
async def unified_dispatch_stream(
    request: Request,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    """Stream dispatches with durable replay after reconnects and restarts."""
    cursor: int | None = None
    if last_event_id is not None:
        try:
            cursor = int(last_event_id)
        except ValueError as error:
            raise HTTPException(
                status_code=400, detail="Last-Event-ID must be an integer."
            ) from error
        if cursor < 0:
            raise HTTPException(
                status_code=400, detail="Last-Event-ID must be non-negative."
            )

    try:
        queue = live_sync_supervisor.supervisor.register_interface()
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    async def stream_events() -> AsyncIterator[str]:
        last_sent = cursor
        try:
            yield "retry: 3000\n\n"
            events = await asyncio.to_thread(_list_unified_dispatch_events)
            events.reverse()
            latest = _dispatch_event_record(events[-1]) if events else None

            if cursor is None:
                snapshot_id = latest["event_id"] if latest else None
                yield _format_sse(
                    "snapshot",
                    latest or {"event_id": None, "created_at": None, "envelope": None},
                    snapshot_id,
                )
                last_sent = snapshot_id
            elif (
                (latest is not None and cursor > latest["event_id"])
                or (
                    len(events) == UNIFIED_EVENT_REPLAY_LIMIT
                    and cursor < events[0].id
                )
            ):
                reset_id = latest["event_id"] if latest else 0
                yield _format_sse(
                    "reset",
                    latest or {"event_id": None, "created_at": None, "envelope": None},
                    reset_id,
                )
                last_sent = reset_id
            else:
                for event in events:
                    if event.id <= cursor:
                        continue
                    record = _dispatch_event_record(event)
                    yield _format_sse("dispatch", record, event.id)
                    last_sent = event.id

            while not await request.is_disconnected():
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                if message is None:
                    queue.task_done()
                    yield (
                        "event: replay-required\n"
                        'data: {"reason":"subscriber_queue_overflow"}\n\n'
                    )
                    return
                try:
                    notification = json.loads(message)
                    record = notification["data"]
                    event_id = record["event_id"]
                    if event_id <= (last_sent or 0):
                        continue
                    yield _format_sse("dispatch", record, event_id)
                    last_sent = event_id
                finally:
                    queue.task_done()
        finally:
            live_sync_supervisor.supervisor.unregister_interface(queue)

    return StreamingResponse(
        stream_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/v1/status")
def project_status(
    limit: Annotated[int, Query(ge=1, le=100)] = 3,
) -> dict[str, Any]:
    snapshot = get_store().dashboard_snapshot(limit)
    return {
        **asdict(snapshot),
        "total_count": snapshot.total_count,
        "completion_percent": snapshot.completion_percent,
    }


@app.get("/api/v1/export")
def export_project() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        **get_store().export_data(),
    }


@app.post("/api/v1/restore")
def restore_project(request: RestoreRequest) -> dict[str, int | str | None]:
    store = get_store()
    try:
        if request.replace:
            store.validate_export(request.backup)
            current_data = store.export_data()
            safety_backup: str | None = None
            if current_data["tasks"] or current_data["events"]:
                backup_path, _ = write_backup(store)
                safety_backup = str(backup_path)
        else:
            safety_backup = None
        task_count, event_count = store.restore_data(
            request.backup, replace=request.replace
        )
    except ValueError as error:
        _raise_bad_request(error)
    return {
        "tasks_restored": task_count,
        "events_restored": event_count,
        "safety_backup": safety_backup,
    }


@app.post("/api/v1/backups", status_code=201)
def create_backup(request: BackupRequest) -> dict[str, str | int]:
    try:
        backup_path, pruned = write_backup(get_store(), keep=request.keep)
    except ValueError as error:
        _raise_bad_request(error)
    return {"path": str(backup_path), "pruned": pruned}


def _schedule_status() -> dict[str, Any]:
    try:
        path, installed, loaded, last_exit_code = backup_schedule_status(
            get_database_path()
        )
    except SchedulerError as error:
        raise HTTPException(status_code=501, detail=str(error)) from error
    return {
        "path": str(path),
        "installed": installed,
        "loaded": loaded,
        "last_exit_code": last_exit_code,
    }


@app.get("/api/v1/backups/schedule")
def get_backup_schedule() -> dict[str, Any]:
    return _schedule_status()


@app.post("/api/v1/backups/schedule")
def create_backup_schedule(request: BackupRequest) -> dict[str, str | int]:
    try:
        path = install_backup_schedule(get_database_path(), keep=request.keep)
    except (SchedulerError, OSError, ValueError) as error:
        raise HTTPException(status_code=501, detail=str(error)) from error
    return {"path": str(path), "keep": request.keep}


@app.delete("/api/v1/backups/schedule")
def delete_backup_schedule() -> dict[str, str | bool]:
    try:
        path, removed = uninstall_backup_schedule(get_database_path())
    except (SchedulerError, OSError) as error:
        raise HTTPException(status_code=501, detail=str(error)) from error
    return {"path": str(path), "removed": removed}


@app.get("/api/v1/doctor")
def project_doctor() -> dict[str, Any]:
    diagnostics = AetherEngineDoctor(get_database_path()).diagnostics()
    failures = sum(item.status == "FAIL" for item in diagnostics)
    warnings = sum(item.status == "WARN" for item in diagnostics)
    return {
        "healthy": failures == 0,
        "failure_count": failures,
        "warning_count": warnings,
        "diagnostics": [asdict(item) for item in diagnostics],
    }


@app.get("/process")
def run_code(
    input_data: Annotated[
        str,
        Query(min_length=1, max_length=4_000, description="Text to process."),
    ],
) -> dict[str, str]:
    """Process text supplied as the input_data query parameter."""
    if not input_data.strip():
        raise HTTPException(status_code=422, detail="Input cannot be blank.")
    return my_custom_logic(input_data)


def my_custom_logic(user_input: str) -> dict[str, str]:
    """Return a normalized representation of user-provided text."""
    return {"result": f"Processed: {user_input.strip()}"}


def main() -> None:
    """Run the local API service."""
    uvicorn.run(app, host="127.0.0.1", port=8000)
