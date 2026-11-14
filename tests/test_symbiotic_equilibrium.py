import json

import pytest

from aether_engine.symbiotic_equilibrium import (
    MAX_EQUILIBRIUM_BRANCHES,
    SymbioticEquilibriumEngine,
    SystemBranch,
    main,
)


def _branch(
    branch_id="healthy",
    *,
    vitality=0.7,
    energy_draw=0.4,
    harm_index=0,
    is_stale=False,
):
    return SystemBranch(
        branch_id,
        "Archive",
        vitality,
        energy_draw,
        harm_index,
        is_stale,
    )


def test_registration_enforces_zero_harm_and_copies_branch():
    engine = SymbioticEquilibriumEngine()
    original = _branch()

    assert engine.register_branch(original)
    original.vitality = 0.1
    snapshot = engine.system_health_report()
    assert snapshot["branches"][0]["vitality"] == 0.7
    assert snapshot["zero_harm_verified"] is True

    assert not engine.register_branch(_branch("harmful", harm_index=0.01))
    snapshot = engine.system_health_report()
    assert [branch["branch_id"] for branch in snapshot["branches"]] == ["healthy"]
    assert "BLOCKED" in snapshot["stewardship_log"][-1]


@pytest.mark.parametrize(
    ("branch", "message"),
    [
        (_branch(vitality=-0.1), "vitality"),
        (_branch(vitality=1.1), "vitality"),
        (_branch(energy_draw=-1), "energy_draw"),
        (_branch(harm_index=-0.1), "harm_index"),
        (_branch(vitality=float("nan")), "finite"),
        (_branch(vitality=True), "finite"),
        (_branch(" "), "branch_id"),
        (
            SystemBranch("bad-time", "Archive", 0.5, 0.2, 0, last_active_utc="yesterday"),
            "last_active_utc",
        ),
    ],
)
def test_registration_rejects_invalid_branch_data(branch, message):
    with pytest.raises(ValueError, match=message):
        SymbioticEquilibriumEngine().register_branch(branch)


def test_registration_rejects_duplicate_and_excess_branches():
    engine = SymbioticEquilibriumEngine()
    engine.register_branch(_branch())
    with pytest.raises(ValueError, match="already registered"):
        engine.register_branch(_branch())

    full = SymbioticEquilibriumEngine()
    for index in range(MAX_EQUILIBRIUM_BRANCHES):
        full.register_branch(_branch(f"branch-{index}"))
    with pytest.raises(ValueError, match="No more than"):
        full.register_branch(_branch("overflow"))


def test_nurture_boosts_only_active_harmless_branches_and_caps_vitality():
    engine = SymbioticEquilibriumEngine()
    engine.register_branch(_branch("weaker", vitality=0.4))
    engine.register_branch(_branch("stronger", vitality=0.8))
    engine.register_branch(_branch("stale", vitality=0.2, is_stale=True))

    notes = engine.nurture_and_advance()
    branches = {
        branch["branch_id"]: branch
        for branch in engine.system_health_report()["branches"]
    }

    assert len(notes) == 2
    assert branches["weaker"]["vitality"] == 0.496
    assert branches["stronger"]["vitality"] == 0.864
    assert branches["stale"]["vitality"] == 0.2
    assert engine.nurture_and_advance(1.0)
    assert engine.ecosystem["weaker"].vitality == 1
    assert engine.ecosystem["stronger"].vitality == 1


@pytest.mark.parametrize("boost", [-0.1, 1.1, float("inf"), True])
def test_nurture_rejects_invalid_boost(boost):
    with pytest.raises(ValueError):
        SymbioticEquilibriumEngine().nurture_and_advance(boost)


def test_prune_removes_stale_and_below_floor_only_then_composts():
    engine = SymbioticEquilibriumEngine(vitality_floor=0.25)
    engine.register_branch(_branch("healthy", vitality=0.8))
    engine.register_branch(_branch("weak", vitality=0.2))
    engine.register_branch(_branch("stale", vitality=0.9, is_stale=True))

    notes = engine.prune_and_compost()
    snapshot = engine.system_health_report()

    assert len(notes) == 2
    assert [branch["branch_id"] for branch in snapshot["branches"]] == ["healthy"]
    assert snapshot["composted_count"] == 2
    assert {item["recycled_id"] for item in snapshot["compost_archive"]} == {
        "weak",
        "stale",
    }
    assert snapshot["zero_harm_verified"] is True


def test_harmful_branch_is_never_composted_if_invariant_is_bypassed():
    engine = SymbioticEquilibriumEngine()
    engine.register_branch(_branch())
    engine.ecosystem["healthy"].harm_index = 0.5

    engine.prune_and_compost()
    snapshot = engine.system_health_report()

    assert snapshot["compost_archive"] == []
    assert snapshot["zero_harm_verified"] is True


def test_cli_runs_reproducible_demo_and_emits_json(capsys):
    assert main([]) == 0
    report = json.loads(capsys.readouterr().out)

    assert report["cycle"] == "demo"
    assert any("PRUNED" in note for note in report["cycle_notes"])
    assert any("ADVANCE" in note for note in report["cycle_notes"])
    assert report["snapshot"]["zero_harm_verified"] is True
    assert report["snapshot"]["composted_count"] == 1
