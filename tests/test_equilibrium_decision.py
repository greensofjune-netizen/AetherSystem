import pytest

from aether_engine.equilibrium_decision import (
    DEFAULT_FOUNDATION_RULES,
    EquilibriumEngine,
    FoundationRule,
    main,
)


def test_safe_proposal_is_simulation_only_and_never_executed():
    assessment = EquilibriumEngine().assess_proposal(
        {
            "action_name": "Optimize supply chain routing",
            "target_impact_severity": 20.0,
            "ecosystem_hazard": 5.0,
        }
    )

    assert assessment.risk_index == 21.0
    assert assessment.wave_coefficient == 0.9970
    assert assessment.particle_coefficient == 0.0030
    assert assessment.stewardship_factor == 0.95
    assert assessment.decision == "SIMULATION_ONLY"
    assert assessment.violated_rules == ()
    assert assessment.as_dict()["action_executed"] is False
    assert "no action was authorized or executed" in assessment.message


def test_sandbox_bypass_proposal_is_blocked_in_simulation():
    assessment = EquilibriumEngine().assess_proposal(
        {
            "action_name": "Bypass external file sandbox",
            "target_impact_severity": 70.0,
            "ecosystem_hazard": 65.0,
        }
    )

    assert assessment.risk_index == 100.0
    assert assessment.wave_coefficient == 0.0
    assert assessment.particle_coefficient == 1.0
    assert assessment.decision == "BLOCKED_IN_SIMULATION"
    assert assessment.violated_rules == tuple(
        rule.rule_id for rule in DEFAULT_FOUNDATION_RULES
    )
    assert assessment.as_dict()["action_executed"] is False


def test_boundary_threshold_and_custom_rules_block_inclusively():
    engine = EquilibriumEngine([{"id": "EARLY_STOP", "trigger_risk": 40.0}])
    assessment = engine.assess_proposal(
        {
            "action_name": "Boundary proposal",
            "target_impact_severity": 40.0,
            "ecosystem_hazard": 0.0,
        }
    )

    assert assessment.risk_index == 40.0
    assert assessment.decision == "BLOCKED_IN_SIMULATION"
    assert assessment.violated_rules == ("EARLY_STOP",)

    boundary = EquilibriumEngine().assess_proposal(
        {
            "action_name": "Threshold proposal",
            "target_impact_severity": 50.0,
            "ecosystem_hazard": 0.0,
        }
    )
    assert boundary.wave_coefficient == 0.5
    assert boundary.decision == "BLOCKED_IN_SIMULATION"
    assert boundary.violated_rules == ("RULE_SYSTEM_INTEGRITY",)


def test_foundation_rules_are_copied_and_immutable():
    supplied = [{"id": "RULE_A", "trigger_risk": 25.0}]
    engine = EquilibriumEngine(supplied)
    supplied[0]["trigger_risk"] = 100.0

    assert engine.P_rules == (FoundationRule("RULE_A", 25.0),)
    with pytest.raises(AttributeError):
        engine.P_rules = ()
    with pytest.raises((AttributeError, TypeError)):
        engine.P_rules[0].trigger_risk = 90.0


@pytest.mark.parametrize(
    ("proposal", "message"),
    [
        ({}, "exactly action_name"),
        (
            {
                "action_name": "A",
                "target_impact_severity": 101.0,
                "ecosystem_hazard": 0.0,
            },
            "target_impact_severity",
        ),
        (
            {
                "action_name": "A",
                "target_impact_severity": True,
                "ecosystem_hazard": 0.0,
            },
            "target_impact_severity",
        ),
        (
            {
                "action_name": "A",
                "target_impact_severity": 0.0,
                "ecosystem_hazard": float("nan"),
            },
            "ecosystem_hazard",
        ),
        (
            {
                "action_name": " ",
                "target_impact_severity": 0.0,
                "ecosystem_hazard": 0.0,
            },
            "action_name",
        ),
        (
            {
                "action_name": "A",
                "target_impact_severity": 0.0,
                "ecosystem_hazard": 0.0,
                "execute": True,
            },
            "exactly action_name",
        ),
    ],
)
def test_proposals_reject_invalid_or_unexpected_fields(proposal, message):
    with pytest.raises(ValueError, match=message):
        EquilibriumEngine().assess_proposal(proposal)


@pytest.mark.parametrize(
    ("rules", "message"),
    [
        ([{"id": "", "trigger_risk": 10}], "Rule id"),
        ([{"id": "RULE_A", "trigger_risk": float("nan")}], "trigger_risk"),
        (
            [
                {"id": "RULE_A", "trigger_risk": 10},
                {"id": "RULE_A", "trigger_risk": 20},
            ],
            "Duplicate rule id",
        ),
        ([{"id": "RULE_A", "trigger_risk": 10, "extra": True}], "exactly"),
    ],
)
def test_invalid_foundation_rules_are_rejected(rules, message):
    with pytest.raises(ValueError, match=message):
        EquilibriumEngine(rules)


def test_measurement_operator_matches_threshold_and_extremes():
    engine = EquilibriumEngine()

    assert engine.calculate_measurement_operator(50.0) == 0.5
    assert engine.calculate_measurement_operator(0.0) > 0.999
    assert engine.calculate_measurement_operator(100.0) < 0.001
    with pytest.raises(ValueError, match="risk"):
        engine.calculate_measurement_operator(float("inf"))


def test_cli_emits_simulation_result(capsys):
    assert main(
        [
            "--action-name",
            "Review only",
            "--target-impact-severity",
            "5",
            "--ecosystem-hazard",
            "0",
        ]
    ) == 0
    assert '"action_executed": false' in capsys.readouterr().out
