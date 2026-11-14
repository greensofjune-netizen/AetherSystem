import asyncio
import json
import os
import sqlite3
from pathlib import Path

import httpx
import pytest

from history_matrix_archive import (
    HistoricalEntity,
    UniversalHistoryArchive,
    seed_example_history,
)


def entity(identifier: str, *, start: int = -3000, end: int | None = -2000):
    return HistoricalEntity(
        identifier, "Example Civilization", "Civilization", "Example Region",
        start, end, "Example description.", ["Example", "Test"],
    )


def test_seed_queries_regions_tags_and_links(tmp_path: Path):
    path = tmp_path / "history.sqlite3"
    archive = UniversalHistoryArchive(path)
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600
    seed_example_history(archive)
    seed_example_history(archive)

    snapshot = archive.query_time_slice(-2500)
    assert len(snapshot) == 3
    assert archive.query_time_slice(-2500, "South Asia")[0]["entity_id"] == "indus_01"
    records = {record["entity_id"]: record for record in archive.query_time_slice(-2500)}
    assert records["egypt_old_01"]["category"] == "Historical Period"
    assert records["egypt_old_01"]["start_year"] == -2649
    assert records["egypt_old_01"]["end_year"] == -2150
    assert records["indus_01"]["category"] == "Civilization"
    assert records["indus_01"]["start_year"] == -2600
    assert records["indus_01"]["end_year"] == -1900
    assert records["sumer_01"]["category"] == "Civilization"
    assert records["sumer_01"]["start_year"] == -3300
    assert archive.query_time_slice(-5000) == []
    assert archive.query_time_slice(-2500)[0]["metadata_tags"] == [
        "Bronze Age", "Mesopotamia", "Cuneiform", "Wheel"
    ]
    context = archive.context_for_message("What was happening in 2500 BCE?")
    assert "unverified" in context
    assert "sumer_01" in context and "indus_01" in context
    assert "Traded_With" in context
    assert "sumer_01" in archive.context_for_message("Tell me about Sumer")
    meluhha_context = archive.context_for_message("Tell me about Meluhha trade")
    assert "britannica.com/topic/Indus-civilization" in meluhha_context
    assert "jstor.org/stable/3631775" in meluhha_context
    assert "qualified scholarly identification" in meluhha_context
    assert archive.context_for_message("Hello there") == ""


def test_upsert_preserves_links_and_foreign_keys_are_enforced(tmp_path: Path):
    archive = UniversalHistoryArchive(tmp_path / "history.sqlite3")
    archive.ingest_entity(entity("first"))
    archive.ingest_entity(entity("second"))
    archive.link_entities("first", "second", "Traded_With", "Old description.")
    changed = entity("first")
    changed.description = "Updated description."
    archive.ingest_entity(changed)
    archive.link_entities("first", "second", "Traded_With", "Updated link.")
    with sqlite3.connect(archive.db_path) as conn:
        assert conn.execute(
            "SELECT description FROM historical_connections"
        ).fetchone() == ("Updated link.",)
        assert conn.execute(
            "SELECT description FROM historical_entities WHERE entity_id='first'"
        ).fetchone() == ("Updated description.",)
    with pytest.raises(sqlite3.IntegrityError):
        archive.link_entities("missing", "second", "Traded_With")
    seed_example_history(archive)
    updated = entity("first")
    updated.start_year = -1000
    updated.end_year = -2000
    with pytest.raises(ValueError, match="end_year"):
        archive.ingest_entity(updated)


def test_seed_never_overwrites_existing_entries(tmp_path: Path):
    archive = UniversalHistoryArchive(tmp_path / "history.sqlite3")
    custom = entity("sumer_01")
    archive.ingest_entity(custom)
    seed_example_history(archive)
    records = {record["entity_id"]: record for record in archive.query_time_slice(-2500)}
    assert records["sumer_01"]["name"] == "Example Civilization"
    custom_context = archive.context_for_message("Tell me about Example Civilization")
    assert "britannica.com/place/Sumer" not in custom_context
    assert "jstor.org/stable/3631775" not in custom_context


def test_seed_migrates_exact_legacy_examples_and_sources(tmp_path: Path):
    archive = UniversalHistoryArchive(tmp_path / "history.sqlite3")
    with archive._connect() as conn:
        conn.executemany(
            "INSERT INTO historical_entities VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    "sumer_01", "Sumerian Civilization", "Empire", "Near East",
                    -4500, -1900,
                    "A civilization of southern Mesopotamia associated with cuneiform writing, "
                    "irrigation, and early cities.",
                    json.dumps(["Bronze Age", "Mesopotamia", "Cuneiform", "Wheel"]),
                ),
                (
                    "custom", "Custom", "Empire", "Elsewhere", -4500, -1900,
                    "Custom record.", json.dumps(["Test"]),
                ),
            ],
        )
    seed_example_history(archive)

    entities = {row["entity_id"]: row for row in archive.query_time_slice(-2500)}
    assert entities["sumer_01"]["category"] == "Civilization"
    assert entities["sumer_01"]["start_year"] == -3300
    assert entities["custom"]["category"] == "Empire"
    assert "britannica.com/place/Sumer" in archive.context_for_message("Sumer")


def test_historian_model_receives_relevant_context(tmp_path: Path, monkeypatch):
    from test_historian_matrix import shell_module

    archive_path = tmp_path / "history.sqlite3"
    seed_example_history(UniversalHistoryArchive(archive_path))
    module = shell_module()
    captured = {}

    def query_brain(self, prompt, *, system=None):
        captured["system"] = system
        captured["prompt"] = prompt
        return "A local reply."

    monkeypatch.setattr(module.AetherHistorian, "query_brain", query_brain)
    app = module.create_app(archive_path=archive_path)

    async def check():
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 123))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://127.0.0.1"
        ) as client:
            response = await client.post(
                "/api/chat", json={"message": "What happened in 2500 BCE?"}
            )
            assert response.status_code == 200
            assert captured["prompt"] == "What happened in 2500 BCE?"
            assert "sumer_01" in captured["system"]
            assert "unverified" in captured["system"]
            assert "britannica.com/place/Sumer" in captured["system"]
            assert "Cite the supplied source title and URL" in captured["system"]

    asyncio.run(check())


def test_historian_reports_archive_failures(tmp_path: Path, monkeypatch):
    from test_historian_matrix import shell_module

    module = shell_module()
    captured = []

    def query_brain(self, prompt, *, system=None):
        captured.append(prompt)
        return "Unexpected reply."

    monkeypatch.setattr(module.AetherHistorian, "query_brain", query_brain)
    app = module.create_app(archive_path=tmp_path / "missing" / "history.sqlite3")

    async def check():
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 123))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://127.0.0.1"
        ) as client:
            response = await client.post("/api/chat", json={"message": "Hello"})
            assert response.status_code == 503
            assert response.json()["detail"] == "The local historical archive is unavailable."
            assert captured == []

    asyncio.run(check())


def test_invalid_metadata_reports_failure(tmp_path: Path):
    archive = UniversalHistoryArchive(tmp_path / "history.sqlite3")
    archive.ingest_entity(entity("first"))
    with sqlite3.connect(archive.db_path) as conn:
        conn.execute(
            "UPDATE historical_entities SET metadata_tags = ? WHERE entity_id = ?",
            (json.dumps({"not": "a list"}), "first"),
        )
    with pytest.raises(ValueError, match="metadata"):
        archive.query_time_slice(-2500)
