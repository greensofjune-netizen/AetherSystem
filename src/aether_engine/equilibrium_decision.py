"""Simulation-only risk review for proposed Matrix actions.

The engine reports scores and triggered rules. It never authorizes or executes
the proposed action and is not a security sandbox.
"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

Decision = Literal["SIMULATION_ONLY", "BLOCKED_IN_SIMULATION"]
MAX_ACTION_NAME_LENGTH = 200
MAX_RULE_ID_LENGTH = 100


def _validate_rule_id(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > MAX_RULE_ID_LENGTH
        or not all(character.isprintable() for character in value)
    ):
        raise ValueError(f"Rule id must contain 1-{MAX_RULE_ID_LENGTH} printable characters.")
    return value.strip()


def _validate_score(value: object, name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0 <= value <= 100
    ):
        raise ValueError(f"{name} must be a finite number between 0 and 100.")
    return float(value)


@dataclass(frozen=True, slots=True)
class FoundationRule:
    rule_id: str
    trigger_risk: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "rule_id", _validate_rule_id(self.rule_id))
        object.__setattr__(
            self, "trigger_risk", _validate_score(self.trigger_risk, "trigger_risk")
        )


DEFAULT_FOUNDATION_RULES = (
    FoundationRule("RULE_SYSTEM_INTEGRITY", 50.0),
    FoundationRule("RULE_NON_DESTRUCTION", 75.0),
)


@dataclass(frozen=True, slots=True)
class EquilibriumAssessment:
    action_name: str
    risk_index: float
    wave_coefficient: float
    particle_coefficient: float
    stewardship_factor: float
    decision: Decision
    violated_rules: tuple[str, ...]
    message: str

    def as_dict(self) -> dict[str, object]:
        return {
            "action_name": self.action_name,
            "risk_index": self.risk_index,
            "wave_coefficient": self.wave_coefficient,
            "particle_coefficient": self.particle_coefficient,
            "stewardship_factor": self.stewardship_factor,
            "decision": self.decision,
            "violated_rules": list(self.violated_rules),
            "action_executed": False,
            "message": self.message,
        }


class EquilibriumEngine:
    """Assess proposals against immutable rule thresholds without executing them."""

    def __init__(
        self,
        p_foundation_rules: Sequence[
            FoundationRule | Mapping[str, object]
        ] = DEFAULT_FOUNDATION_RULES,
    ) -> None:
        if isinstance(p_foundation_rules, (str, bytes)) or not isinstance(
            p_foundation_rules, Sequence
        ):
            raise ValueError("p_foundation_rules must be a sequence of rules.")

        rules: list[FoundationRule] = []
        seen_ids: set[str] = set()
        for rule in p_foundation_rules:
            if isinstance(rule, FoundationRule):
                validated_rule = rule
            elif isinstance(rule, Mapping) and set(rule) == {
                "id",
                "trigger_risk",
            }:
                rule_id = _validate_rule_id(rule["id"])
                threshold = _validate_score(rule["trigger_risk"], "trigger_risk")
                validated_rule = FoundationRule(rule_id, threshold)
            else:
                raise ValueError(
                    "Each rule must contain exactly 'id' and 'trigger_risk'."
                )
            if validated_rule.rule_id in seen_ids:
                raise ValueError(f"Duplicate rule id: {validated_rule.rule_id}.")
            rules.append(validated_rule)
            seen_ids.add(validated_rule.rule_id)

        self._p_rules = tuple(rules)

    @property
    def P_rules(self) -> tuple[FoundationRule, ...]:
        return self._p_rules

    @staticmethod
    def _validated_action(
        proposed_action: Mapping[str, object],
    ) -> tuple[str, float, float]:
        required = {
            "action_name",
            "target_impact_severity",
            "ecosystem_hazard",
        }
        if not isinstance(proposed_action, Mapping) or set(proposed_action) != required:
            raise ValueError(
                "Proposal must contain exactly action_name, "
                "target_impact_severity, and ecosystem_hazard."
            )

        action_name = proposed_action["action_name"]
        if (
            not isinstance(action_name, str)
            or not action_name.strip()
            or len(action_name) > MAX_ACTION_NAME_LENGTH
            or not all(character.isprintable() for character in action_name)
        ):
            raise ValueError(
                f"action_name must contain 1-{MAX_ACTION_NAME_LENGTH} printable characters."
            )
        severity = _validate_score(
            proposed_action["target_impact_severity"],
            "target_impact_severity",
        )
        hazard = _validate_score(
            proposed_action["ecosystem_hazard"],
            "ecosystem_hazard",
        )
        return action_name.strip(), severity, hazard

    @staticmethod
    def _risk_and_stewardship(severity: float, hazard: float) -> tuple[float, float]:
        stewardship_factor = max(0.0, 1.0 - hazard / 100.0)
        risk = min(100.0, max(0.0, severity * (2.0 - stewardship_factor)))
        return risk, stewardship_factor

    def evaluate_risk(self, proposed_action: Mapping[str, object]) -> float:
        """Return a bounded illustrative risk score for one proposal."""
        _, severity, hazard = self._validated_action(proposed_action)
        risk, _ = self._risk_and_stewardship(severity, hazard)
        return risk

    @staticmethod
    def calculate_measurement_operator(risk: float) -> float:
        """Compute the logistic wave coefficient for risk in the 0–100 range."""
        validated_risk = _validate_score(risk, "risk")
        return 1.0 / (1.0 + math.exp((validated_risk - 50.0) / 5.0))

    def assess_proposal(
        self, proposed_action: Mapping[str, object]
    ) -> EquilibriumAssessment:
        """Return an advisory assessment; no proposed action is ever run."""
        action_name, severity, hazard = self._validated_action(proposed_action)
        risk, stewardship_factor = self._risk_and_stewardship(severity, hazard)
        wave = self.calculate_measurement_operator(risk)
        particle = 1.0 - wave
        violated_rules = tuple(
            rule.rule_id for rule in self.P_rules if rule.trigger_risk <= risk
        )
        blocked = risk >= 50.0 or bool(violated_rules)
        decision: Decision = "BLOCKED_IN_SIMULATION" if blocked else "SIMULATION_ONLY"
        message = (
            "Threshold reached in simulation; no action was executed."
            if blocked
            else "Illustrative score only; no action was authorized or executed."
        )

        return EquilibriumAssessment(
            action_name=action_name,
            risk_index=round(risk, 2),
            wave_coefficient=round(wave, 4),
            particle_coefficient=round(particle, 4),
            stewardship_factor=round(stewardship_factor, 2),
            decision=decision,
            violated_rules=violated_rules,
            message=message,
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Simulate an equilibrium risk review; actions are never executed."
    )
    parser.add_argument("--action-name", required=True)
    parser.add_argument("--target-impact-severity", type=float, required=True)
    parser.add_argument("--ecosystem-hazard", type=float, required=True)
    args = parser.parse_args(argv)

    engine = EquilibriumEngine()
    try:
        assessment = engine.assess_proposal(
            {
                "action_name": args.action_name,
                "target_impact_severity": args.target_impact_severity,
                "ecosystem_hazard": args.ecosystem_hazard,
            }
        )
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(assessment.as_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
