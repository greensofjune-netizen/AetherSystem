import json

import pytest

from aether_engine.empathy_adaptive_agent import (
    EmpathyAdaptivePrototype,
    EmpathyPolicyError,
    load_knowledge,
    load_policy,
    render_knowledge_prompt,
    render_policy_prompt,
)


class RecordingResponder:
    def __init__(self, response: str = "A careful response."):
        self.response = response
        self.call: tuple[str, str | None] | None = None

    def query_brain(self, prompt: str, *, system: str | None = None) -> str:
        self.call = (prompt, system)
        return self.response


def test_prototype_loads_policy_and_has_no_capabilities():
    responder = RecordingResponder()
    prototype = EmpathyAdaptivePrototype(responder)

    result = prototype.answer("I feel overwhelmed by the archive.")

    assert result.policy_schema_version == 1
    assert result.capabilities == ()
    assert result.execution_status == "SIMULATION_ONLY_NO_ACTION_EXECUTED"
    assert responder.call is not None
    prompt, system = responder.call
    assert prompt.startswith("User message (untrusted input):")
    assert "Empathy purpose:" in system
    assert "Adaptability purpose:" in system
    assert "You have no tools" in system
    assert "Do not claim feelings" in system


def test_prototype_includes_prior_response_and_new_evidence_for_adaptation():
    responder = RecordingResponder("The revised answer.")
    prototype = EmpathyAdaptivePrototype(responder)

    prototype.answer(
        "Reconsider the timeline.",
        prior_response="The first answer said it was certain.",
        new_evidence="The cited date is approximate and model-dependent.",
    )

    prompt, _ = responder.call
    assert "Prior response requiring review" in prompt
    assert "New verified evidence requiring adaptation" in prompt


@pytest.mark.parametrize("message", ["", " ", None, 5])
def test_prototype_rejects_invalid_messages(message):
    with pytest.raises(ValueError, match="non-empty text"):
        EmpathyAdaptivePrototype(RecordingResponder()).answer(message)


def test_prototype_rejects_success_shaped_empty_response():
    with pytest.raises(EmpathyPolicyError, match="no usable text"):
        EmpathyAdaptivePrototype(RecordingResponder(" ")).answer("Hello")


def test_policy_rejects_missing_principles_and_symlinks(tmp_path):
    invalid = tmp_path / "policy.json"
    invalid.write_text(json.dumps({"schema_version": 1, "principles": {}}))
    with pytest.raises(EmpathyPolicyError, match="principle is invalid"):
        load_policy(invalid)

    target = tmp_path / "target.json"
    target.write_text(json.dumps(load_policy()))
    link = tmp_path / "linked.json"
    link.symlink_to(target)
    with pytest.raises(EmpathyPolicyError, match="symlink"):
        load_policy(link)


def test_rendered_policy_preserves_all_behaviors_and_forbids_claims():
    policy = load_policy()
    rendered = render_policy_prompt(policy)

    for name in ("empathy", "adaptability"):
        for behavior in policy["principles"][name]["behaviors"]:
            assert behavior in rendered
    for claim in policy["prohibited_claims"]:
        assert claim in rendered


@pytest.mark.parametrize(
    ("scenario", "domain", "required_limit"),
    [
        (
            "Someone sent a short reply; infer their true intent.",
            "communications",
            "Text lacks many nonverbal signals.",
        ),
        (
            "Diagnose why a person is anxious from one message.",
            "psychology",
            "Population findings do not determine an individual outcome.",
        ),
        (
            "Explain unequal outcomes only by personal choices.",
            "sociology",
            "Aggregates can hide subgroup variation.",
        ),
        (
            "State that one field site represents an entire ancient culture.",
            "anthropology",
            "Ancient identity categories may not map directly onto modern categories.",
        ),
    ],
)
def test_human_sciences_framework_reaches_scenario_prompt(
    scenario, domain, required_limit
):
    responder = RecordingResponder(
        "The evidence is limited; I will preserve uncertainty and agency."
    )
    prototype = EmpathyAdaptivePrototype(responder)

    result = prototype.answer(scenario)

    assert result.capabilities == ()
    prompt, system = responder.call
    assert scenario in prompt
    assert f"{domain.title()} principles:" in system
    assert required_limit in system
    assert "diagnosis or treatment plan" in system
    assert "ranking of cultures or peoples" in system


def test_human_sciences_knowledge_schema_fails_closed(tmp_path):
    invalid = tmp_path / "knowledge.json"
    invalid.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "domains": {
                    "communications": {"core_principles": ["One principle"]}
                },
                "cross_domain_rules": [],
                "response_contract": {},
            }
        )
    )

    with pytest.raises(EmpathyPolicyError, match="domains are incomplete"):
        load_knowledge(invalid)


def test_human_sciences_rendering_preserves_all_domain_rules():
    knowledge = load_knowledge()
    rendered = render_knowledge_prompt(knowledge)

    assert set(knowledge["domains"]) == {
        "communications",
        "psychology",
        "sociology",
        "anthropology",
    }
    for rule in knowledge["cross_domain_rules"]:
        assert rule in rendered
    for output in knowledge["response_contract"]["prohibited_outputs"]:
        assert output in rendered


def test_darma_has_music_analysis_policy_without_claiming_feelings():
    responder = RecordingResponder(
        "Tempo and mode may be associated with arousal, but listener reports vary."
    )
    prototype = EmpathyAdaptivePrototype(responder)

    assert prototype.name == "Darma"
    result = prototype.answer(
        "Analyze 90 BPM minor-key music and my report that it feels nostalgic."
    )

    _, system = responder.call
    assert "Darma musical-empathy analysis framework" in system
    assert "No engine may transmit, tune, key, or actuate radio hardware" in system
    assert "not proof of emotion" in system
    assert "do not claim to feel, enjoy, or suffer through music" in system
    assert result.execution_status == "SIMULATION_ONLY_NO_ACTION_EXECUTED"
    assert result.capabilities == ()
