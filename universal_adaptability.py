"""Zero-harm pattern sharing across a small simulated ecosystem."""

from __future__ import annotations

import math
from dataclasses import dataclass


def _require_finite_number(value: object, field_name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ValueError(f"{field_name} must be a finite number.")
    return float(value)


def _require_unit_interval(value: object, field_name: str) -> None:
    numeric_value = _require_finite_number(value, field_name)
    if not 0.0 <= numeric_value <= 1.0:
        raise ValueError(f"{field_name} must be between 0.0 and 1.0.")


@dataclass
class KnowledgePattern:
    name: str
    energy_cost: float
    harm_score: float
    success_rate: float = 0.5
    shared_count: int = 0

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Check mutable pattern data before it is adopted or shared."""
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Pattern name cannot be empty.")
        self.name = self.name.strip()
        _require_finite_number(self.energy_cost, "energy_cost")
        if self.energy_cost < 0.0:
            raise ValueError("energy_cost cannot be negative.")

        _require_finite_number(self.harm_score, "harm_score")
        if self.harm_score < 0.0:
            raise ValueError("harm_score cannot be negative.")

        _require_unit_interval(self.success_rate, "success_rate")
        if (
            isinstance(self.shared_count, bool)
            or not isinstance(self.shared_count, int)
            or self.shared_count < 0
        ):
            raise ValueError("shared_count must be a non-negative integer.")


class EcosystemNode:
    """A node with a local playbook that accepts only zero-harm patterns."""

    def __init__(self, node_id: str, resilience: float = 0.8) -> None:
        if not isinstance(node_id, str) or not node_id.strip():
            raise ValueError("node_id cannot be empty.")
        _require_unit_interval(resilience, "resilience")

        self.node_id = node_id.strip()
        self.resilience = resilience
        self.local_playbook: dict[str, KnowledgePattern] = {}
        self.completed_cycles = 0
        self._adaptation_count = 0

    def adopt_pattern(self, pattern: KnowledgePattern) -> bool:
        pattern.validate()
        if pattern.harm_score > 0.0 or pattern.name in self.local_playbook:
            return False

        self.local_playbook[pattern.name] = KnowledgePattern(
            name=pattern.name,
            energy_cost=pattern.energy_cost,
            harm_score=pattern.harm_score,
            success_rate=pattern.success_rate,
            shared_count=pattern.shared_count + 1,
        )
        return True

    def tackle_obstacle(self, difficulty: float) -> tuple[bool, str]:
        _require_unit_interval(difficulty, "difficulty")
        _require_unit_interval(self.resilience, "resilience")
        for pattern in self.local_playbook.values():
            pattern.validate()
        safe_options = [
            pattern
            for pattern in self.local_playbook.values()
            if pattern.harm_score == 0.0
        ]
        if not safe_options:
            return False, "No safe strategies available"

        best = max(
            safe_options,
            key=lambda pattern: pattern.success_rate
            / max(pattern.energy_cost, 0.1),
        )
        effective_skill = (best.success_rate * 0.7) + (self.resilience * 0.3)

        if effective_skill >= difficulty:
            best.success_rate = min(0.99, best.success_rate + 0.05)
            self.completed_cycles += 1
            return True, best.name

        self._adaptation_count += 1
        adapted_name = f"{best.name}_adapted_v{self._adaptation_count}"
        while adapted_name in self.local_playbook:
            self._adaptation_count += 1
            adapted_name = f"{best.name}_adapted_v{self._adaptation_count}"

        self.local_playbook[adapted_name] = KnowledgePattern(
            name=adapted_name,
            energy_cost=max(0.2, best.energy_cost * 0.9),
            harm_score=0.0,
            success_rate=min(0.95, best.success_rate + 0.18),
        )
        return False, f"Synthesized new approach: {adapted_name}"


class CollectiveProgressEngine:
    """Coordinate safe pattern adoption and generation-by-generation progress."""

    def __init__(self) -> None:
        self.nodes: list[EcosystemNode] = []
        self.shared_commons: dict[str, KnowledgePattern] = {}

    def register_node(self, node: EcosystemNode) -> None:
        if any(existing.node_id == node.node_id for existing in self.nodes):
            raise ValueError(f"Node {node.node_id!r} is already registered.")
        self.nodes.append(node)
        for pattern in self.shared_commons.values():
            node.adopt_pattern(pattern)

    def broadcast_breakthrough(self, pattern: KnowledgePattern) -> int:
        pattern.validate()
        if pattern.harm_score > 0.0:
            return 0

        shared_pattern = KnowledgePattern(
            name=pattern.name,
            energy_cost=pattern.energy_cost,
            harm_score=pattern.harm_score,
            success_rate=pattern.success_rate,
            shared_count=pattern.shared_count,
        )
        self.shared_commons[shared_pattern.name] = shared_pattern

        adoptions = 0
        for node in self.nodes:
            if node.adopt_pattern(shared_pattern):
                adoptions += 1
        return adoptions

    def step_generation(self, environmental_challenge: float) -> list[str]:
        _require_unit_interval(environmental_challenge, "environmental_challenge")
        telemetry: list[str] = []
        for node in self.nodes:
            solved, detail = node.tackle_obstacle(environmental_challenge)
            if solved:
                proven = node.local_playbook[detail]
                spread = self.broadcast_breakthrough(proven)
                telemetry.append(
                    f"[{node.node_id}] Cleared challenge "
                    f"({environmental_challenge:.2f}) using '{detail}' "
                    f"-> Shared with {spread} peers"
                )
            else:
                telemetry.append(
                    f"[{node.node_id}] Hit resistance "
                    f"({environmental_challenge:.2f}) -> {detail}"
                )
        return telemetry


if __name__ == "__main__":
    engine = CollectiveProgressEngine()
    seed = KnowledgePattern(
        name="observe_and_balance",
        energy_cost=1.0,
        harm_score=0.0,
        success_rate=0.55,
    )
    engine.broadcast_breakthrough(seed)

    for name, resilience in [
        ("Node_Alpha", 0.9),
        ("Node_Beta", 0.65),
        ("Node_Gamma", 0.75),
    ]:
        engine.register_node(EcosystemNode(node_id=name, resilience=resilience))

    for generation in range(1, 5):
        challenge = round(0.55 + (generation * 0.1), 2)
        print(
            f"\n--- Generation {generation} "
            f"(Challenge Difficulty: {challenge}) ---"
        )
        for line in engine.step_generation(challenge):
            print(line)
