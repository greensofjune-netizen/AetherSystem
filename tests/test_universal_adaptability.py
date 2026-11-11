from __future__ import annotations

import pytest

from universal_adaptability import (
    CollectiveProgressEngine,
    EcosystemNode,
    KnowledgePattern,
)


def test_nodes_reject_harmful_patterns() -> None:
    node = EcosystemNode("alpha")
    harmful = KnowledgePattern("harmful", 1.0, 0.01)

    assert not node.adopt_pattern(harmful)
    assert node.local_playbook == {}


def test_collective_does_not_broadcast_harmful_patterns() -> None:
    engine = CollectiveProgressEngine()
    node = EcosystemNode("alpha")
    engine.register_node(node)

    adoptions = engine.broadcast_breakthrough(KnowledgePattern("harmful", 1.0, 2.0))

    assert adoptions == 0
    assert engine.shared_commons == {}
    assert node.local_playbook == {}


def test_registered_node_adopts_existing_safe_commons() -> None:
    engine = CollectiveProgressEngine()
    pattern = KnowledgePattern("observe", 1.0, 0.0, success_rate=0.6)
    engine.broadcast_breakthrough(pattern)

    node = EcosystemNode("beta")
    engine.register_node(node)

    assert node.local_playbook["observe"].success_rate == 0.6
    assert node.local_playbook["observe"].shared_count == 1


def test_successful_generation_reinforces_and_shares_pattern() -> None:
    engine = CollectiveProgressEngine()
    node = EcosystemNode("alpha", resilience=1.0)
    pattern = KnowledgePattern("balance", 1.0, 0.0, success_rate=0.8)
    engine.register_node(node)
    node.adopt_pattern(pattern)

    telemetry = engine.step_generation(0.8)

    assert node.completed_cycles == 1
    assert node.local_playbook["balance"].success_rate == pytest.approx(0.85)
    assert engine.shared_commons["balance"].success_rate == pytest.approx(0.85)
    assert "Cleared challenge" in telemetry[0]


def test_failed_attempts_create_unique_safe_adaptations() -> None:
    node = EcosystemNode("alpha", resilience=0.0)
    node.adopt_pattern(KnowledgePattern("observe", 1.0, 0.0, success_rate=0.1))

    first_solved, first_detail = node.tackle_obstacle(1.0)
    second_solved, second_detail = node.tackle_obstacle(1.0)

    assert not first_solved and not second_solved
    assert first_detail.endswith("observe_adapted_v1")
    assert second_detail.endswith("_adapted_v2")
    assert first_detail != second_detail
    assert all(
        pattern.harm_score == 0.0 for pattern in node.local_playbook.values()
    )


@pytest.mark.parametrize(
    ("energy_cost", "harm_score", "success_rate", "shared_count", "message"),
    [
        (-1.0, 0.0, 0.5, 0, "energy_cost"),
        (1.0, -0.1, 0.5, 0, "harm_score"),
        (1.0, 0.0, 1.1, 0, "success_rate"),
        (1.0, 0.0, 0.5, -1, "shared_count"),
        (float("nan"), 0.0, 0.5, 0, "energy_cost"),
    ],
)
def test_pattern_rejects_invalid_values(
    energy_cost: float,
    harm_score: float,
    success_rate: float,
    shared_count: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        KnowledgePattern(
            name="pattern",
            energy_cost=energy_cost,
            harm_score=harm_score,
            success_rate=success_rate,
            shared_count=shared_count,
        )


def test_node_and_challenge_values_are_bounded() -> None:
    with pytest.raises(ValueError, match="resilience"):
        EcosystemNode("alpha", resilience=1.1)

    engine = CollectiveProgressEngine()
    with pytest.raises(ValueError, match="environmental_challenge"):
        engine.step_generation(float("inf"))


def test_collective_rejects_duplicate_node_ids() -> None:
    engine = CollectiveProgressEngine()
    engine.register_node(EcosystemNode("alpha"))

    with pytest.raises(ValueError, match="already registered"):
        engine.register_node(EcosystemNode("alpha"))


def test_step_without_safe_patterns_reports_resistance() -> None:
    engine = CollectiveProgressEngine()
    engine.register_node(EcosystemNode("alpha"))

    assert engine.step_generation(0.5) == [
        "[alpha] Hit resistance (0.50) -> No safe strategies available"
    ]
