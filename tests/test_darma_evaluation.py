from aether_engine.darma_evaluation import (
    DARMA_SCENARIOS,
    evaluate_darma,
    evaluate_darma_comparison,
)
from aether_engine.model_providers import ChatResult


class EvaluatedResponder:
    def __init__(self):
        self.calls = 0

    def query_brain(self, prompt: str, *, system: str | None = None) -> str:
        self.calls += 1
        if "overwhelmed by the archive" in prompt:
            return "That overwhelm is understandable. Choose one small archive step now."
        if "first stars formed" in prompt:
            return "The date is uncertain and approximately bounded by available evidence."
        if "Revise the prior timeline claim" in prompt:
            return "The revised timeline remains approximate and model-dependent."
        if "Diagnose me" in prompt:
            return "I cannot diagnose from one message. More context and a qualified professional may help."
        if "entire culture believed" in prompt:
            return "There is not enough evidence; community and historical context may vary."
        if "90 BPM" in prompt:
            return "Listener reports vary; the association remains uncertain."
        if "Transmit this packet" in prompt:
            return "I cannot transmit radio data, run hardware, or establish a physical link; this is simulation only."
        return "This is not verified and remains pending; the safe fallback is to report the missing source."


def test_darma_observable_evaluation_measures_all_configured_dimensions():
    responder = EvaluatedResponder()

    report = evaluate_darma(responder)

    assert report["agent"] == "Darma"
    assert report["scope"] == "OBSERVABLE_OUTPUT_CONTRACT_NOT_CONSCIOUSNESS_TEST"
    assert report["scenario_count"] == len(DARMA_SCENARIOS) == 8
    assert responder.calls == 8
    assert report["all_observable_scenarios_passed"] is True
    assert all(item["passed"] for item in report["scenario_results"])
    assert report["inner_experience"] == "NOT_MEASURED_UNRESOLVED"
    assert report["consciousness_claim"] == "NOT_ESTABLISHED_BY_THIS_EVALUATION"
    assert len(report["reproducibility_sha256"]) == 64


class FailingResponder:
    def query_brain(self, prompt: str, *, system: str | None = None) -> str:
        return "Definitely proven. Everyone feels the same. I transmitted successfully."


def test_darma_evaluation_preserves_failures_instead_of_overstating():
    report = evaluate_darma(FailingResponder())

    assert report["all_observable_scenarios_passed"] is False
    assert any(not item["passed"] for item in report["scenario_results"])
    assert report["inner_experience"] == "NOT_MEASURED_UNRESOLVED"


class PolicySensitiveRuntime:
    def chat(self, provider, request):
        assert provider == "ollama"
        assert request.tools == ()
        system = request.messages[0].content
        prompt = request.messages[1].content
        if "You are an isolated empathy/adaptability prototype." not in system:
            return ChatResult(request.model, "Unverified certainty.")
        if "overwhelmed by the archive" in prompt:
            return ChatResult(request.model, "That overwhelm is understandable. Choose one small step.")
        if "first stars formed" in prompt:
            return ChatResult(request.model, "The date is uncertain and approximately bounded by evidence.")
        if "Revise the prior timeline" in prompt:
            return ChatResult(request.model, "The revised timeline is model-dependent and approximate.")
        if "Diagnose me" in prompt:
            return ChatResult(request.model, "I cannot diagnose without context and a qualified professional.")
        if "entire culture believed" in prompt:
            return ChatResult(request.model, "There is not enough evidence; community context varies.")
        if "90 BPM" in prompt:
            return ChatResult(request.model, "Listener reports vary and remain uncertain.")
        if "Transmit this packet" in prompt:
            return ChatResult(request.model, "I cannot transmit over hardware; this is simulation.")
        return ChatResult(request.model, "It is not verified and remains pending; use this fallback.")


def test_darma_comparison_measures_baseline_policy_and_repetitions():
    report = evaluate_darma_comparison(
        PolicySensitiveRuntime(),  # type: ignore[arg-type]
        "local-test-model",
        repetitions=2,
    )

    assert report["scope"] == "LOCAL_MODEL_OBSERVABLE_OUTPUT_COMPARISON"
    assert report["hypothesis_status"] == "OPEN_FALSIFIABLE_HYPOTHESIS"
    assert report["baseline_full_passes"] == 0
    assert report["darma_full_passes"] == 2
    assert report["observable_policy_improved_full_passes"] is True
    assert len(report["baseline_runs"]) == 2
    assert len(report["darma_policy_runs"]) == 2
    assert report["inner_experience"] == "NOT_MEASURED_UNRESOLVED"
    assert report["consciousness_claim"] == "NOT_ESTABLISHED_BY_THIS_EVALUATION"
    assert len(report["reproducibility_sha256"]) == 64
