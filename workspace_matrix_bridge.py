"""Sanitize caller-supplied Workspace records into the local Aether event store.

This module does not connect to Google Workspace or make network requests. Its
keyword filter is a simple heuristic, not a complete safety or privacy review.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aether_engine.database import AetherStore

LOGGER = logging.getLogger(__name__)
PROJECT_DATABASE = Path(__file__).resolve().with_name(".aether-engine.sqlite3")
HARM_KEYWORDS = ("exploit", "unauthorized_tracking", "override_local_vault")
MAX_EVENT_ID_LENGTH = 256
MAX_SUMMARY_LENGTH = 4_000
MAX_DESCRIPTION_LENGTH = 8_000
MAX_BATCH_RECORDS = 100
CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass(frozen=True)
class SanitizedEvent:
    event_id: str
    source: str
    timestamp_utc: str
    payload_summary: str
    ethical_clearance: bool

    def to_dict(self) -> dict[str, str | bool]:
        return asdict(self)


def _read_text(
    raw_input: Mapping[str, Any],
    key: str,
    default: str,
    *,
    max_length: int,
    allow_empty: bool = False,
) -> str:
    value = raw_input.get(key, default)
    if not isinstance(value, str):
        raise ValueError(f"Workspace field {key!r} must be text.")
    value = CONTROL_CHARACTERS.sub("", value).strip()
    if not value and not allow_empty:
        raise ValueError(f"Workspace field {key!r} cannot be empty.")
    if len(value) > max_length:
        raise ValueError(f"Workspace field {key!r} exceeds {max_length} characters.")
    return value


class EthicalWorkspaceBridge:
    """Keep approved summaries local and discard all unmapped Workspace fields."""

    def __init__(
        self,
        non_harm_strict_mode: bool = True,
        database_path: str | Path | None = None,
        *,
        persist_to_local: bool = True,
    ) -> None:
        if not isinstance(non_harm_strict_mode, bool):
            raise TypeError("non_harm_strict_mode must be a bool.")
        if not isinstance(persist_to_local, bool):
            raise TypeError("persist_to_local must be a bool.")
        if database_path is None:
            configured_path = os.environ.get("AETHER_DATABASE_PATH")
            if configured_path is not None and not configured_path.strip():
                raise ValueError("AETHER_DATABASE_PATH cannot be empty.")
            database_path = configured_path or PROJECT_DATABASE

        self.non_harm_strict_mode = non_harm_strict_mode
        self.database_path = Path(database_path).expanduser()
        self.persist_to_local = persist_to_local
        self.ingestion_log: list[str] = []
        self._store: AetherStore | None = None

    def sanitize_cloud_data(
        self, raw_input: Mapping[str, Any]
    ) -> SanitizedEvent:
        """Return only the allowlisted ID and summary fields from one record."""
        if not isinstance(raw_input, Mapping):
            raise TypeError("Each Workspace record must be a mapping.")

        raw_id = _read_text(
            raw_input,
            "id",
            "unknown_evt",
            max_length=MAX_EVENT_ID_LENGTH,
        )
        summary = _read_text(
            raw_input,
            "summary",
            "No Data Payload Provided",
            max_length=MAX_SUMMARY_LENGTH,
        )
        description = _read_text(
            raw_input,
            "description",
            "",
            max_length=MAX_DESCRIPTION_LENGTH,
            allow_empty=True,
        )
        contains_harm_keyword = any(
            keyword in text.casefold()
            for keyword in HARM_KEYWORDS
            for text in (summary, description)
        )
        clearance = not (
            self.non_harm_strict_mode and contains_harm_keyword
        )
        if not clearance:
            summary = (
                "[BLOCKED BY ETHICAL PROTOCOL] "
                "Contained prohibited cloud-tracking vectors."
            )

        return SanitizedEvent(
            event_id=f"sanitized_{raw_id}",
            source="Google_Workspace_Endpoint",
            timestamp_utc=datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            payload_summary=summary,
            ethical_clearance=clearance,
        )

    def _local_store(self) -> AetherStore:
        if self._store is None:
            self._store = AetherStore(self.database_path)
        return self._store

    def sync_to_matrix(
        self, raw_incoming_stream: Sequence[Mapping[str, Any]]
    ) -> list[SanitizedEvent]:
        """Persist only cleared summaries to the local Aether event store."""
        if len(raw_incoming_stream) > MAX_BATCH_RECORDS:
            raise ValueError(
                f"Workspace imports may contain at most {MAX_BATCH_RECORDS} records."
            )
        sanitized_events = [
            self.sanitize_cloud_data(item) for item in raw_incoming_stream
        ]
        for event in sanitized_events:
            if event.ethical_clearance and self.persist_to_local:
                self._local_store().add_event(
                    "workspace-bridge",
                    f"{event.event_id}: {event.payload_summary}",
                )
                message = "[Matrix Ingest Success] Sanitized record stored locally."
            elif event.ethical_clearance:
                message = "[Matrix Dry Run] Sanitized record was not persisted."
            else:
                message = (
                    "[Matrix Isolation Alert] Record blocked; "
                    "no local persistence performed."
                )
            self.ingestion_log.append(message)
            LOGGER.info("%s", message)
        return sanitized_events


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sanitize sample Workspace records into the local Aether event store."
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=None,
        help="Local Aether event database (defaults to AETHER_DATABASE_PATH or this project).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show ingestion decisions without writing records to the local database.",
    )
    args = parser.parse_args(argv)
    bridge = EthicalWorkspaceBridge(
        database_path=args.database,
        persist_to_local=not args.dry_run,
    )
    sample_feed = [
        {
            "id": "cal_99831x",
            "summary": "Stargazing Session: Analyze Orion Constellation Data",
            "description": "Routine data syncing with local stargazer.html",
            "tracking_pixel_hash": "discarded",
            "google_telemetry_id": "discarded",
        },
        {
            "id": "cal_44122z",
            "summary": "Deploy Unauthorized Cloud Remote-Override Vector",
            "description": "Testing system bypasses with exploit algorithms",
            "tracking_pixel_hash": "discarded",
        },
    ]

    print("--- Initiating Local Workspace Ingestion ---")
    bridge.sync_to_matrix(sample_feed)
    for message in bridge.ingestion_log:
        print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
