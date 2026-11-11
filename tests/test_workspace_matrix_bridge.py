from __future__ import annotations

from datetime import datetime

import pytest

from aether_engine.database import AetherStore
from workspace_matrix_bridge import EthicalWorkspaceBridge


def test_sanitization_keeps_only_allowlisted_workspace_fields(tmp_path):
    bridge = EthicalWorkspaceBridge(database_path=tmp_path / "events.sqlite3")

    event = bridge.sanitize_cloud_data(
        {
            "id": "calendar-42",
            "summary": "Stargazing session",
            "description": "Routine planning",
            "tracking_pixel_hash": "private-tracking-value",
            "google_telemetry_id": "private-telemetry-value",
        }
    )

    assert event.event_id == "sanitized_calendar-42"
    assert event.payload_summary == "Stargazing session"
    assert event.ethical_clearance
    assert set(event.to_dict()) == {
        "event_id",
        "source",
        "timestamp_utc",
        "payload_summary",
        "ethical_clearance",
    }
    assert datetime.fromisoformat(event.timestamp_utc.replace("Z", "+00:00"))


def test_strict_filter_blocks_keyword_matches_without_persisting(tmp_path):
    database_path = tmp_path / "events.sqlite3"
    bridge = EthicalWorkspaceBridge(database_path=database_path)

    events = bridge.sync_to_matrix(
        [
            {
                "id": "calendar-43",
                "summary": "Planning",
                "description": "Check for EXPLOIT attempts",
            }
        ]
    )

    assert not events[0].ethical_clearance
    assert events[0].payload_summary.startswith("[BLOCKED BY ETHICAL PROTOCOL]")
    assert "EXPLOIT" not in events[0].payload_summary
    assert not database_path.exists()
    assert "no local persistence" in bridge.ingestion_log[0]


def test_sync_persists_only_cleared_events_to_local_aether_store(tmp_path):
    database_path = tmp_path / "events.sqlite3"
    bridge = EthicalWorkspaceBridge(database_path=database_path)

    events = bridge.sync_to_matrix(
        [
            {"id": "calendar-44", "summary": "Stargazing", "description": ""},
            {
                "id": "calendar-45",
                "summary": "Override",
                "description": "override_local_vault",
            },
        ]
    )

    stored = AetherStore(database_path).list_events(topic="workspace-bridge")
    assert len(stored) == 1
    assert "sanitized_calendar-44: Stargazing" in stored[0].message
    assert events[0].ethical_clearance
    assert not events[1].ethical_clearance


def test_batch_is_validated_before_any_persistence(tmp_path):
    database_path = tmp_path / "events.sqlite3"
    bridge = EthicalWorkspaceBridge(database_path=database_path)

    with pytest.raises(ValueError, match="summary.*must be text"):
        bridge.sync_to_matrix(
            [
                {"id": "calendar-46", "summary": "Valid"},
                {"id": "calendar-47", "summary": None},
            ]
        )

    assert not database_path.exists()


def test_dry_run_and_disabled_strict_filter_are_explicit(tmp_path):
    database_path = tmp_path / "events.sqlite3"
    bridge = EthicalWorkspaceBridge(
        non_harm_strict_mode=False,
        database_path=database_path,
        persist_to_local=False,
    )

    events = bridge.sync_to_matrix(
        [
            {
                "id": "calendar-48",
                "summary": "Exploit test",
                "description": "exploit",
            }
        ]
    )

    assert events[0].ethical_clearance
    assert not database_path.exists()
    assert "dry run" in bridge.ingestion_log[0].lower()
