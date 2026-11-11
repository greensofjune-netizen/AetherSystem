"""Simulated Matrix agent routing and illustrative memory estimates."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any

MEMORY_REFERENCE_GB = 5.3
GOVERNOR_OVERHEAD_GB = 0.6
BLOCKED_TERMS = ("exploit", "unauthorized_tracking")
MAX_LOG_ENTRIES = 200
_CHART_LABELS = {
    "astro_agent": "Astronomy Node (Skyfield)",
    "kinetic_agent": "Propulsion Node (Kinetics)",
    "history_agent": "History Node (Ledger Archive)",
}


@dataclass
class AgentMetadata:
    name: str
    specialty: str
    vram_overhead_gb: float
    active_status: bool = True


class AgentGovernor:
    """Route simulated tasks; keyword checks are not a security or ethics guarantee."""

    def __init__(self) -> None:
        self.registry = {
            "astro_agent": AgentMetadata("Astronomy Vector Node", "Astronomy", 1.2),
            "kinetic_agent": AgentMetadata("Propulsion Spec Node", "Propulsion", 1.5),
            "history_agent": AgentMetadata("Ancestral Ledger Node", "History", 0.8),
        }
        self.orchestration_log: list[str] = []
        self._lock = Lock()

    def _record(self, timestamp: str, outcome: str, node: str) -> None:
        self.orchestration_log.append(f"[{timestamp}] {outcome}: {node}")
        del self.orchestration_log[:-MAX_LOG_ENTRIES]

    def route_task(
        self, task_description: str, domain: str, execution_payload: dict[str, Any]
    ) -> dict[str, Any]:
        if not isinstance(task_description, str) or not task_description.strip():
            raise ValueError("Task description must be non-empty text.")
        if len(task_description) > 4000:
            raise ValueError("Task description exceeds 4,000 characters.")
        if not isinstance(domain, str) or not domain.strip() or len(domain) > 100:
            raise ValueError("Domain must be non-empty text of at most 100 characters.")
        if not isinstance(execution_payload, dict):
            raise ValueError("Execution payload must be a JSON object.")
        try:
            payload_text = json.dumps(
                execution_payload, ensure_ascii=False, allow_nan=False
            )
        except (TypeError, ValueError, RecursionError) as error:
            raise ValueError("Execution payload must contain valid JSON data.") from error
        if len(payload_text.encode("utf-8")) > 32_000:
            raise ValueError("Execution payload exceeds 32,000 UTF-8 bytes.")

        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        )
        screened_text = (task_description + "\n" + domain + "\n" + payload_text).lower()
        with self._lock:
            if any(term in screened_text for term in BLOCKED_TERMS):
                self._record(timestamp, "REJECTED", "governor_core")
                return {
                    "status": "REJECTED",
                    "assigned_node": "governor_core",
                    "message": "Task rejected by the illustrative keyword screen.",
                    "timestamp": timestamp,
                }
            match = next(
                (
                    (node_id, metadata)
                    for node_id, metadata in self.registry.items()
                    if metadata.active_status
                    and metadata.specialty.casefold() == domain.strip().casefold()
                ),
                None,
            )
            if match is None:
                self._record(timestamp, "UNROUTABLE", "governor_core")
                return {
                    "status": "UNROUTABLE",
                    "assigned_node": "governor_core",
                    "message": "No active simulated agent matches the requested domain.",
                    "timestamp": timestamp,
                }
            node_id, metadata = match
            self._record(timestamp, "SIMULATED", node_id)
            return {
                "status": "SIMULATED",
                "assigned_node": node_id,
                "agent_name": metadata.name,
                "message": (
                    f"Simulated routing to {metadata.name}; estimated memory "
                    f"{metadata.vram_overhead_gb:g} GB. No task was executed."
                ),
                "output_data": execution_payload,
                "timestamp": timestamp,
            }

    def allocation_chart(self) -> dict[str, Any]:
        """Return the requested bar-chart shape from active estimated allocations."""
        with self._lock:
            allocations = [
                (
                    _CHART_LABELS.get(node_id, metadata.name),
                    metadata.vram_overhead_gb,
                )
                for node_id, metadata in self.registry.items()
                if metadata.active_status
            ]
        allocations.append(("Governor Overhead", GOVERNOR_OVERHEAD_GB))
        return {
            "metadata": {
                "chart_type": "bar",
                "chart_title": "Illustrative Agent Memory Estimates",
                "orientation": "horizontal",
                "stacking": "grouped",
                "x_axis_title": "Estimated Unified Memory (Gigabytes)",
                "y_axis_title": "Active Simulated Agents",
                "unit_symbol": " GB",
                "unit_position": "suffix",
                "scale_type": "linear",
                "value_tiers": [],
                "reference_threshold_gb": MEMORY_REFERENCE_GB,
                "estimated_total_gb": round(sum(value for _, value in allocations), 3),
                "measured": False,
            },
            "labels": [label for label, _ in allocations],
            "datasets": [
                {
                    "label": "Estimated Memory",
                    "axis": "primary",
                    "data": [
                        {
                            "value_raw": value,
                            "tooltip_text": f"{label}: {value:g} GB estimated",
                        }
                        for label, value in allocations
                    ],
                }
            ],
        }

    def verify_route(self, domain: str, result: dict[str, Any]) -> bool:
        """Check that a simulated assignment still names an active matching node."""
        with self._lock:
            node_id = result.get("assigned_node")
            metadata = self.registry.get(node_id) if isinstance(node_id, str) else None
            return bool(
                result.get("status") == "SIMULATED"
                and metadata is not None
                and metadata.active_status
                and metadata.specialty.casefold() == domain.strip().casefold()
            )

    @staticmethod
    def encode_chart(chart: dict[str, Any]) -> str:
        chart_bytes = json.dumps(chart, ensure_ascii=False).encode("utf-8")
        return base64.b64encode(chart_bytes).decode("ascii")

    def encoded_chart(self) -> str:
        return self.encode_chart(self.allocation_chart())


def main() -> int:
    governor = AgentGovernor()
    for description, domain, payload in (
        (
            "Compute current zenith star over Upland, CA",
            "Astronomy",
            {"latitude": 34.0975, "longitude": -117.6484, "target": "Rigel"},
        ),
        (
            "Deploy tracking payload across network nodes",
            "Propulsion",
            {"engine_id": "shkval_01", "injection_vector": "unauthorized_tracking_pixel"},
        ),
    ):
        result = governor.route_task(description, domain, payload)
        print(f'{result["status"]} -> {result["assigned_node"]}: {result["message"]}')
    print(f'chartjs_spec: "{governor.encoded_chart()}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
