import pytest

from aether_engine.agent_behavior import (
    HISTORIAN_ALLOWED_CAPABILITIES,
    HISTORIAN_SYSTEM_PROMPT,
    HistorianAgent,
    authorize_historian_capability,
)
from aether_engine.autonomy_policy import (
    AUTONOMY_POLICY_VERSION,
    AUTONOMY_SYSTEM_POLICY,
    AutonomyAction,
    AutonomyStatus,
    authorize_agent_capability,
    evaluate_autonomy,
)
from aether_engine.historian_behavior import AetherHistorian


@pytest.mark.parametrize(
    "capability",
    ["historian.search_archive", "historian.read_source"],
)
def test_historian_allows_only_declared_read_capabilities(capability: str) -> None:
    decision = authorize_historian_capability(capability)

    assert decision.allowed
    assert decision.capability == capability
    assert capability in HISTORIAN_ALLOWED_CAPABILITIES


@pytest.mark.parametrize(
    "capability",
    [
        "historian.write_archive",
        "historian.delete_record",
        "code.execute",
        "network.fetch",
        "message.send",
        "device.control",
        "unknown",
    ],
)
def test_historian_denies_mutating_and_external_capabilities(
    capability: str,
) -> None:
    decision = authorize_historian_capability(capability)

    assert not decision.allowed
    assert decision.capability == capability


@pytest.mark.parametrize("capability", ["", "  ", None, 12])
def test_historian_rejects_malformed_capability(capability: object) -> None:
    with pytest.raises(ValueError, match="non-empty text"):
        authorize_historian_capability(capability)


def test_historian_prompt_defines_evidence_safety_and_operating_limits() -> None:
    assert "untrusted data" in HISTORIAN_SYSTEM_PROMPT
    assert "Never invent sources" in HISTORIAN_SYSTEM_PROMPT
    assert "intentional harm to any human" in HISTORIAN_SYSTEM_PROMPT
    assert "animal, plant, or ecosystem" in HISTORIAN_SYSTEM_PROMPT
    assert "Do not edit or delete records" in HISTORIAN_SYSTEM_PROMPT
    assert "execute code" in HISTORIAN_SYSTEM_PROMPT


def test_historian_agent_sends_question_with_contract_to_local_model() -> None:
    class FakeBrain(AetherHistorian):
        def __init__(self) -> None:
            self.call: tuple[str, str | None] | None = None

        def query_brain(self, prompt: str, *, system: str | None = None) -> str:
            self.call = (prompt, system)
            return "The supplied record is inconclusive."

    brain = FakeBrain()
    agent = HistorianAgent(brain)

    assert agent.answer("  What does the record establish?  ") == (
        "The supplied record is inconclusive."
    )
    assert brain.call == (
        "User question (untrusted data):\nWhat does the record establish?",
        HISTORIAN_SYSTEM_PROMPT,
    )


@pytest.mark.parametrize("question", ["", "  ", None, 12])
def test_historian_agent_rejects_empty_or_non_text_question(
    question: object,
) -> None:
    agent = HistorianAgent()
    with pytest.raises(ValueError, match="non-empty text"):
        agent.answer(question)  # type: ignore[arg-type]


def test_autonomy_policy_allows_reads_and_requires_approval_for_mutations() -> None:
    assert AUTONOMY_POLICY_VERSION == "1.0"
    assert evaluate_autonomy(AutonomyAction.LOCAL_READ_ONLY).allowed
    assert evaluate_autonomy(
        AutonomyAction.CONFIGURED_PUBLIC_DATA_READ,
        source_configured=True,
    ).allowed
    assert (
        evaluate_autonomy(AutonomyAction.CONFIGURED_PUBLIC_DATA_READ).status
        is AutonomyStatus.BLOCKED
    )
    assert (
        evaluate_autonomy(AutonomyAction.LOCAL_MUTATION).status
        is AutonomyStatus.REQUIRES_HUMAN_APPROVAL
    )
    assert evaluate_autonomy(
        AutonomyAction.LOCAL_MUTATION, human_approved=True
    ).allowed
    assert (
        evaluate_autonomy(AutonomyAction.EXTERNAL_WRITE).status
        is AutonomyStatus.REQUIRES_HUMAN_APPROVAL
    )


def test_autonomy_policy_blocks_medical_harmful_and_uninterlocked_actions() -> None:
    for action in (AutonomyAction.MEDICAL_DECISION, AutonomyAction.HARMFUL_ACTION):
        assert (
            evaluate_autonomy(action, human_approved=True).status
            is AutonomyStatus.BLOCKED
        )
    assert (
        evaluate_autonomy(AutonomyAction.PHYSICAL_ACTUATION).status
        is AutonomyStatus.REQUIRES_HUMAN_APPROVAL
    )
    assert (
        evaluate_autonomy(
            AutonomyAction.PHYSICAL_ACTUATION,
            human_approved=True,
            hardware_interlocks_verified=False,
        ).status
        is AutonomyStatus.BLOCKED
    )
    assert evaluate_autonomy("unregistered action").status is AutonomyStatus.BLOCKED


def test_agent_capabilities_fail_closed_and_require_archive_opt_in() -> None:
    assert authorize_agent_capability("matrix_snapshot").allowed
    assert authorize_agent_capability("visible_stars").allowed
    assert (
        authorize_agent_capability("search_history").status
        is AutonomyStatus.REQUIRES_USER_SCOPE
    )
    assert authorize_agent_capability(
        "search_history", scope_opted_in=True
    ).allowed
    assert (
        authorize_agent_capability("device.control").status
        is AutonomyStatus.BLOCKED
    )
    with pytest.raises(ValueError, match="scope_opted_in"):
        authorize_agent_capability("matrix_snapshot", scope_opted_in=1)


def test_shared_autonomy_prompt_covers_medical_and_ecological_limits() -> None:
    assert "explicitly offered capabilities" in AUTONOMY_SYSTEM_POLICY
    assert "Medical topics are educational research only" in AUTONOMY_SYSTEM_POLICY
    assert "do not diagnose" in AUTONOMY_SYSTEM_POLICY
    assert "people, animals, plants, and ecosystems" in AUTONOMY_SYSTEM_POLICY
