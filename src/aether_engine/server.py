from __future__ import annotations

import ipaddress
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Annotated, Any, Literal, NoReturn

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .ai_bridge import LocalAirGappedEngine
from .backups import DEFAULT_BACKUP_RETENTION, write_backup
from .database import AetherStore
from .engine_doctor import AetherEngineDoctor
from .historian import CoPilotHistorian
from .scheduler import (
    SchedulerError,
    backup_schedule_status,
    install_backup_schedule,
    uninstall_backup_schedule,
)

ReasoningEffort = Literal["none", "low", "medium", "high", "xhigh", "max"]
TaskPriority = Literal["low", "normal", "high"]
TaskStatus = Literal["pending", "done"]

app = FastAPI(
    title="Aether Engine API",
    description="Loopback-only REST API for Aether Engine project operations.",
    version="1.0.0",
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
    allow_headers=["Content-Type"],
)

engine = LocalAirGappedEngine()
inference_lock = Lock()


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChatCompletionRequest(StrictRequest):
    prompt: str = Field(min_length=1, max_length=32_768)
    reasoning_effort: ReasoningEffort = "medium"


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


class RestoreRequest(StrictRequest):
    backup: dict[str, Any]
    replace: bool = False


class BackupRequest(StrictRequest):
    keep: int = Field(default=DEFAULT_BACKUP_RETENTION, ge=1, le=10_000)


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


@app.middleware("http")
async def require_loopback_client(request: Request, call_next: Any) -> Any:
    """Keep local database and host operations inaccessible to remote clients."""
    client = request.client
    if client is None:
        return JSONResponse(
            status_code=403, content={"detail": "Loopback clients only."}
        )
    try:
        address = ipaddress.ip_address(client.host)
    except ValueError:
        return JSONResponse(
            status_code=403, content={"detail": "Loopback clients only."}
        )
    if not address.is_loopback:
        return JSONResponse(
            status_code=403, content={"detail": "Loopback clients only."}
        )
    return await call_next(request)


@app.get("/health")
def health_check() -> dict[str, str | bool]:
    """Report server health and whether the configured model file is present."""
    return {
        "status": "healthy",
        "model": engine.model_path.name,
        "model_available": engine.model_path.is_file(),
    }


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
def create_chat_completion(
    request: ChatCompletionRequest,
) -> ChatCompletionResponse:
    """Generate a completion using the configured local model."""
    prompt = request.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=422, detail="Prompt cannot be blank.")

    with inference_lock:
        result = engine.execute_local_inference(
            prompt=prompt,
            reasoning_effort=request.reasoning_effort,
        )

    if result.get("status") != "SUCCESS":
        raise HTTPException(
            status_code=503,
            detail={
                "status": result.get("status", "INFERENCE_UNAVAILABLE"),
                "message": result.get("output", "Local inference is unavailable."),
            },
        )

    output = result.get("output")
    if not isinstance(output, str):
        raise HTTPException(
            status_code=502,
            detail="Local model returned an invalid completion response.",
        )
    model = result.get("model", engine.model_path.name)
    if not isinstance(model, str):
        raise HTTPException(
            status_code=502,
            detail="Local model returned an invalid model identifier.",
        )
    return ChatCompletionResponse(model=model, response=output, status="success")


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
        )
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
