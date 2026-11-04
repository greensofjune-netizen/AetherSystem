from __future__ import annotations

import os
from threading import Lock
from typing import Literal

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .ai_bridge import LocalAirGappedEngine

ReasoningEffort = Literal["none", "low", "medium", "high", "xhigh", "max"]

app = FastAPI(
    title="Local AI Bridge Service",
    description="Local API for the Aether Engine inference backend.",
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
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

engine = LocalAirGappedEngine()
inference_lock = Lock()


class ChatCompletionRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=32_768)
    reasoning_effort: ReasoningEffort = "medium"


class ChatCompletionResponse(BaseModel):
    model: str
    response: str
    status: str
    tokens_used: int | None = None


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


def main() -> None:
    """Run the local API service."""
    uvicorn.run(app, host="127.0.0.1", port=8000)
