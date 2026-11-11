"""Aristotle-specific read-only Matrix and historical archive views."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from agent_governor import AgentGovernor
from history_matrix_archive import UniversalHistoryArchive

LOGGER = logging.getLogger(__name__)


def archive_path(project: Path) -> Path:
    return Path(os.environ.get("AETHER_HISTORY_ARCHIVE", str(project / "universal_history.sqlite3"))).expanduser()


def existing_archive(project: Path) -> Path:
    path = archive_path(project)
    if path.is_symlink() or not path.is_file():
        raise HTTPException(503, "Historical archive is missing or is a symlink.")
    return path


def historical_context(project: Path, message: str) -> str:
    path = existing_archive(project)
    try:
        return UniversalHistoryArchive(path, read_only=True).context_for_message(message)
    except (OSError, sqlite3.Error, ValueError) as error:
        LOGGER.warning("Historical archive lookup failed: %s", error)
        raise HTTPException(503, "Historical archive could not be read.") from error


def render_index(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    text = text.replace("<title>Galileo</title>", "<title>Matrix Aristotle</title>")
    text = text.replace('  <script src="/galileo.js" defer></script>',
                        '  <link rel="stylesheet" href="/aristotle.css">\n'
                        '  <script src="/aristotle.js" defer></script>\n'
                        '  <script src="/galileo.js" defer></script>')
    text = text.replace(">GALILEO<", ">MATRIX ARISTOTLE<")
    text = text.replace("GALILEO CAN MAKE MISTAKES", "ARISTOTLE CAN MAKE MISTAKES")
    text = text.replace("AETHER / GALILEO", "AETHER / MATRIX ARISTOTLE")
    text = text.replace("Message Galileo", "Message Aristotle")
    text = text.replace("native Galileo app", "native Matrix Aristotle app")
    text = text.replace("Galileo spaces", "Aristotle spaces")
    text = text.replace(
        '<button type="button" class="tab" data-tab="matrix">Matrix actions</button>',
        '<button type="button" class="tab" data-tab="history">History archive</button>'
        '<button type="button" class="tab" data-tab="matrix">Matrix engine</button>',
    )
    text = text.replace(
        '<div class="attachment-hint" id="message-count">',
        '<label class="history-opt-in"><input type="checkbox" id="include-history"> '
        'Use matching local history archive excerpts in this message</label>'
        '<div class="attachment-hint" id="message-count">',
    )
    text = text.replace(
        '<section id="matrix-panel"',
        '''<section id="history-panel" class="panel module-panel" aria-labelledby="history-heading" hidden>
          <h2 id="history-heading">Historian archive</h2>
          <p>Search existing historical records locally. Archive data is unverified and is sent to Ollama only when explicitly selected in chat.</p>
          <form id="history-form" aria-label="Search historical archive">
            <label for="history-query">Search name, description, region or category</label>
            <input id="history-query" type="search" maxlength="200" required>
            <button type="submit">Search archive</button>
          </form>
          <p id="history-status" role="status"></p><ul id="history-results"></ul>
        </section>
        <section id="matrix-panel"''',
    )
    text = text.replace(
        '<h2 id="matrix-heading">Matrix actions</h2>',
        '''<h2 id="matrix-heading">Matrix engine</h2>
          <p>System telemetry is simulated; the governor does not execute agents or measure memory.</p>
          <button type="button" id="matrix-refresh">Refresh engine overview</button>
          <p id="matrix-overview" role="status"></p>
          <table><caption>Illustrative agent memory estimates</caption>
          <thead><tr><th scope="col">Component</th><th scope="col">Estimated GB</th></tr></thead>
          <tbody id="governor-allocations"></tbody></table>
          <p id="governor-summary"></p>
          <form id="governor-form" aria-label="Simulate agent routing">
            <label for="governor-domain">Simulated agent domain</label>
            <select id="governor-domain"><option>Astronomy</option><option>Propulsion</option><option>History</option></select>
            <label for="governor-task">Task description</label>
            <input id="governor-task" maxlength="4000" required>
            <button type="submit">Simulate routing</button>
          </form>
          <p id="governor-result" role="status"></p>''',
    )
    text = text.replace(
        "Chat history and selected text/images are saved locally and sent only to local Ollama.",
        "Chat history and selected text/images are saved locally and sent only to local Ollama. "
        "History archive excerpts are included only when selected.",
    )
    return text


class GovernorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_description: str = Field(min_length=1, max_length=4000)
    domain: str = Field(min_length=1, max_length=100)
    execution_payload: dict[str, Any]


def install_aristotle_routes(app: FastAPI, project: Path) -> None:
    governor = AgentGovernor()

    @app.get("/api/aristotle/history")
    def search_history(q: str = Query(min_length=1, max_length=200)) -> dict[str, Any]:
        if not q.strip():
            raise HTTPException(422, "Enter a search term.")
        path = existing_archive(project)
        pattern = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        try:
            with sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True) as db:
                db.row_factory = sqlite3.Row
                rows = db.execute(
                    "SELECT entity_id, name, category, region, start_year, end_year, "
                    "substr(description, 1, 1000) AS description FROM historical_entities "
                    "WHERE name LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\' "
                    "OR region LIKE ? ESCAPE '\\' OR category LIKE ? ESCAPE '\\' "
                    "ORDER BY start_year, entity_id LIMIT 50",
                    (pattern,) * 4,
                ).fetchall()
        except sqlite3.Error as error:
            LOGGER.warning("Historical archive search failed: %s", error)
            raise HTTPException(503, "Historical archive could not be read.") from error
        return {"records": [dict(row) for row in rows]}

    @app.get("/api/aristotle/matrix")
    def matrix_overview() -> dict[str, Any]:
        path = Path(os.environ.get(
            "AETHER_HISTORIAN_LOG_FILE", str(project / "historian_telemetry_vault.json")
        )).expanduser()
        if path.is_symlink():
            raise HTTPException(503, "Matrix telemetry file cannot be a symlink.")
        latest = None
        if path.exists():
            try:
                with path.open(encoding="utf-8") as file:
                    entries = json.load(file)
                if not isinstance(entries, list) or not all(isinstance(item, dict) for item in entries):
                    raise ValueError("Invalid telemetry format.")
                latest = entries[-1] if entries else None
            except (OSError, ValueError) as error:
                LOGGER.warning("Matrix telemetry unavailable: %s", error)
                raise HTTPException(503, "Matrix telemetry could not be read.") from error
        return {"latest_simulation": latest, "allocations": governor.allocation_chart()}

    @app.post("/api/aristotle/governor/route")
    def route_governor(entry: GovernorRequest) -> dict[str, Any]:
        try:
            return governor.route_task(entry.task_description, entry.domain, entry.execution_payload)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
