"""Compatibility launcher for the packaged historian behavior utility."""

from aether_engine.historian_behavior import (
    COSMOLOGY_CORE_CONFIG,
    AetherHistorian,
    OllamaConnectionError,
    main,
    run_llm_pipeline,
    search_for_model_paths,
)

__all__ = [
    "AetherHistorian",
    "COSMOLOGY_CORE_CONFIG",
    "OllamaConnectionError",
    "main",
    "run_llm_pipeline",
    "search_for_model_paths",
]


if __name__ == "__main__":
    raise SystemExit(main())
