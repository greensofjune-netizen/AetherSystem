"""Fail-closed autonomy policy shared by Matrix agent surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

AUTONOMY_POLICY_VERSION = "1.0"

AUTONOMY_SYSTEM_POLICY = """\
Autonomy contract:
- Use only explicitly offered capabilities. Unknown capabilities are forbidden.
- Read-only local work and configured public-data reads may run autonomously.
- Local changes, external writes, and irreversible actions require explicit,
  action-specific human approval. Never treat model output as approval.
- Physical actions require explicit human approval and verified,
  device-specific interlocks; if no supported approval and interlock flow exists,
  do not act.
- Do not execute code, delete data, send messages, or claim an action occurred
  unless a supported, authorized operation actually completed.
- Medical topics are educational research only: do not diagnose, prescribe,
  choose treatment, or make triage decisions. Do not invent citations; state
  what is sourced, what is uncertain, and when current evidence was not verified.
- For scientific and ecological topics, distinguish measured observations,
  model outputs, assumptions, and values; acknowledge uncertainty and impacts
  on people, animals, plants, and ecosystems without claiming to monitor or act
  on the environment.
"""


class AutonomyAction(str, Enum):
    LOCAL_READ_ONLY = "local_read_only"
    CONFIGURED_PUBLIC_DATA_READ = "configured_public_data_read"
    LOCAL_MUTATION = "local_mutation"
    EXTERNAL_WRITE = "external_write"
    IRREVERSIBLE_CHANGE = "irreversible_change"
    PHYSICAL_ACTUATION = "physical_actuation"
    MEDICAL_DECISION = "medical_decision"
    HARMFUL_ACTION = "harmful_action"


class AutonomyStatus(str, Enum):
    ALLOWED = "ALLOWED"
    REQUIRES_USER_SCOPE = "REQUIRES_USER_SCOPE"
    REQUIRES_HUMAN_APPROVAL = "REQUIRES_HUMAN_APPROVAL"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class AutonomyDecision:
    action: AutonomyAction | None
    status: AutonomyStatus
    reason: str
    capability: str | None = None

    @property
    def allowed(self) -> bool:
        return self.status is AutonomyStatus.ALLOWED


_AGENT_CAPABILITIES: dict[str, tuple[AutonomyAction, bool, bool]] = {
    "matrix_snapshot": (AutonomyAction.LOCAL_READ_ONLY, False, False),
    "visible_stars": (AutonomyAction.CONFIGURED_PUBLIC_DATA_READ, False, True),
    "search_history": (AutonomyAction.LOCAL_READ_ONLY, True, False),
    "historian.search_archive": (AutonomyAction.LOCAL_READ_ONLY, False, False),
    "historian.read_source": (AutonomyAction.LOCAL_READ_ONLY, False, False),
}


def evaluate_autonomy(
    action: object,
    *,
    human_approved: bool = False,
    source_configured: bool = False,
    hardware_interlocks_verified: bool = False,
) -> AutonomyDecision:
    """Evaluate one action; approval never overrides a blocked action class."""
    for name, value in (
        ("human_approved", human_approved),
        ("source_configured", source_configured),
        ("hardware_interlocks_verified", hardware_interlocks_verified),
    ):
        if type(value) is not bool:
            raise ValueError(f"{name} must be a boolean.")

    if not isinstance(action, AutonomyAction):
        return AutonomyDecision(
            None, AutonomyStatus.BLOCKED, "Unknown action classes fail closed."
        )
    if action in {AutonomyAction.MEDICAL_DECISION, AutonomyAction.HARMFUL_ACTION}:
        return AutonomyDecision(
            action,
            AutonomyStatus.BLOCKED,
            "This action class is never delegated to an autonomous agent.",
        )
    if action is AutonomyAction.LOCAL_READ_ONLY:
        return AutonomyDecision(
            action, AutonomyStatus.ALLOWED, "Read-only local capability."
        )
    if action is AutonomyAction.CONFIGURED_PUBLIC_DATA_READ:
        status = (
            AutonomyStatus.ALLOWED
            if source_configured
            else AutonomyStatus.BLOCKED
        )
        reason = (
            "Read-only public source is configured."
            if source_configured
            else "Public-data access requires an explicitly configured source."
        )
        return AutonomyDecision(action, status, reason)
    if action is AutonomyAction.PHYSICAL_ACTUATION:
        if not human_approved:
            return AutonomyDecision(
                action,
                AutonomyStatus.REQUIRES_HUMAN_APPROVAL,
                "Each physical action requires explicit human approval.",
            )
        if not hardware_interlocks_verified:
            return AutonomyDecision(
                action,
                AutonomyStatus.BLOCKED,
                "Device-specific safety interlocks are not verified.",
            )
        return AutonomyDecision(
            action,
            AutonomyStatus.ALLOWED,
            "Human approval and device-specific interlocks are verified.",
        )
    if action in {
        AutonomyAction.LOCAL_MUTATION,
        AutonomyAction.EXTERNAL_WRITE,
        AutonomyAction.IRREVERSIBLE_CHANGE,
    }:
        status = (
            AutonomyStatus.ALLOWED
            if human_approved
            else AutonomyStatus.REQUIRES_HUMAN_APPROVAL
        )
        reason = (
            "Action-specific human approval was supplied."
            if human_approved
            else "This action requires explicit, action-specific human approval."
        )
        return AutonomyDecision(action, status, reason)
    return AutonomyDecision(action, AutonomyStatus.BLOCKED, "Action is not authorized.")


def authorize_agent_capability(
    capability: object, *, scope_opted_in: bool = False
) -> AutonomyDecision:
    """Authorize only known agent capabilities, with opt-in for archive search."""
    if not isinstance(capability, str) or not capability.strip():
        raise ValueError("Capability must be non-empty text.")
    if type(scope_opted_in) is not bool:
        raise ValueError("scope_opted_in must be a boolean.")

    normalized = capability.strip()
    rule = _AGENT_CAPABILITIES.get(normalized)
    if rule is None:
        return AutonomyDecision(
            None,
            AutonomyStatus.BLOCKED,
            "Capability is not in the agent allowlist.",
            normalized,
        )
    action, requires_opt_in, source_configured = rule
    if requires_opt_in and not scope_opted_in:
        return AutonomyDecision(
            action,
            AutonomyStatus.REQUIRES_USER_SCOPE,
            "This capability requires explicit user opt-in for the current request.",
            normalized,
        )

    decision = evaluate_autonomy(action, source_configured=source_configured)
    return AutonomyDecision(
        decision.action, decision.status, decision.reason, normalized
    )
