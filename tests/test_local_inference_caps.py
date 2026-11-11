from aether_engine.ai_bridge import LocalAirGappedEngine


def test_local_engine_defaults_to_compact_coder_model(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    engine = LocalAirGappedEngine()

    assert engine.model_path == (
        tmp_path
        / "models"
        / "qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"
    )


def test_local_inference_respects_output_token_cap(tmp_path, monkeypatch):
    class Model:
        max_tokens = None

        def create_chat_completion(self, *, messages, max_tokens, temperature):
            self.max_tokens = max_tokens
            return {"choices": [{"message": {"content": "Local answer."}}]}

    model = Model()
    model_path = tmp_path / "model.gguf"
    model_path.touch()
    engine = LocalAirGappedEngine(model_path=model_path)
    monkeypatch.setattr(engine, "_load_model", lambda: model)

    result = engine.execute_local_inference(
        "Explain this.", reasoning_effort="max", max_output_tokens=1500
    )

    assert result["status"] == "SUCCESS"
    assert model.max_tokens == 1500


def test_local_inference_preserves_default_reasoning_budget(tmp_path, monkeypatch):
    class Model:
        max_tokens = None

        def create_chat_completion(self, *, messages, max_tokens, temperature):
            self.max_tokens = max_tokens
            return {"choices": [{"message": {"content": "Local answer."}}]}

    model = Model()
    model_path = tmp_path / "model.gguf"
    model_path.touch()
    engine = LocalAirGappedEngine(model_path=model_path)
    monkeypatch.setattr(engine, "_load_model", lambda: model)

    engine.execute_local_inference("Explain this.", reasoning_effort="max")

    assert model.max_tokens == 4096
