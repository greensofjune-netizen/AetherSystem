"""Educational genesis timeline lifecycle; not live or predictive telemetry."""

from __future__ import annotations

import math
from typing import Any, cast

UNIVERSE_AGE_YEARS = 13.8e9
SECONDS_PER_YEAR = 31_557_600.0


EPOCHS = (
    {
        "id": "inflation",
        "label": "Inflation proposal",
        "age_seconds_min": 1e-36,
        "age_seconds_max": 1e-32,
        "age_label": "10⁻³⁶ to 10⁻³² seconds",
        "claim_status": "MODEL_DEPENDENT",
        "summary": (
            "A proposed early rapid expansion; timing and scale depend on the "
            "inflation model."
        ),
        "source": "NASA CMB overview",
        "source_url": "https://science.nasa.gov/universe/overview/",
    },
    {
        "id": "nucleosynthesis",
        "label": "Primordial nucleosynthesis",
        "age_seconds_min": 180.0,
        "age_seconds_max": 1_200.0,
        "age_label": "3 to 20 minutes",
        "claim_status": "SUPPORTED",
        "summary": (
            "Primordial matter was dominated by hydrogen and helium, with trace "
            "light nuclei."
        ),
        "source": "NASA NTRS Big Bang Nucleosynthesis",
        "source_url": "https://ntrs.nasa.gov/citations/19950044203",
    },
    {
        "id": "recombination",
        "label": "Recombination and CMB",
        "age_seconds_min": 380_000 * SECONDS_PER_YEAR,
        "age_seconds_max": 380_000 * SECONDS_PER_YEAR,
        "age_label": "about 380,000 years",
        "claim_status": "SUPPORTED",
        "summary": (
            "Neutral atoms formed, the cosmic fog cleared, and CMB photons began "
            "free travel."
        ),
        "source": "NASA CMB baby picture",
        "source_url": (
            "https://science.nasa.gov/universe/stories/quick-reads/"
            "what-can-we-learn-from-the-universes-baby-picture/"
        ),
    },
    {
        "id": "first-stars",
        "label": "First stars and reionization",
        "age_seconds_min": 100_000_000 * SECONDS_PER_YEAR,
        "age_seconds_max": 1_000_000_000 * SECONDS_PER_YEAR,
        "age_label": "hundreds of millions to about 1 billion years",
        "claim_status": "SUPPORTED_WITH_UNCERTAINTY",
        "summary": (
            "Early stars and galaxies emitted ultraviolet radiation that reionized "
            "intergalactic hydrogen."
        ),
        "source": "NASA first stars explainer",
        "source_url": (
            "https://science.nasa.gov/mission/webb/science-overview/"
            "science-explainers/what-were-the-first-stars-like/"
        ),
    },
    {
        "id": "solar-system",
        "label": "Solar-system formation",
        "age_seconds_min": (UNIVERSE_AGE_YEARS - 4.6e9) * SECONDS_PER_YEAR,
        "age_seconds_max": (UNIVERSE_AGE_YEARS - 4.6e9) * SECONDS_PER_YEAR,
        "age_label": "about 4.6 billion years ago",
        "claim_status": "SUPPORTED",
        "summary": (
            "The Sun and planets formed from a collapsing cloud and "
            "protoplanetary disk."
        ),
        "source": "NASA planetary systems",
        "source_url": "https://science.nasa.gov/universe/stars/planetary-system/",
    },
    {
        "id": "present",
        "label": "Present-day observers",
        "age_seconds_min": UNIVERSE_AGE_YEARS * SECONDS_PER_YEAR,
        "age_seconds_max": UNIVERSE_AGE_YEARS * SECONDS_PER_YEAR,
        "age_label": "about 13.8 billion years",
        "claim_status": "INTERPRETIVE_WITH_SUPPORTED_AGE",
        "summary": (
            "Scientific observers study the observable universe using physical "
            "models and instrumentation."
        ),
        "source": "NASA universe overview",
        "source_url": "https://science.nasa.gov/universe/overview/",
    },
)


LIFECYCLE = (
    {
        "stage": 1,
        "name": "Research note",
        "status": "COMPLETE",
        "evidence": "UNIVERSAL_GENESIS_RESEARCH_NOTES.md",
    },
    {
        "stage": 2,
        "name": "Verified timeline",
        "status": "COMPLETE_WITH_UNCERTAINTY",
        "evidence": "Six milestones with NASA source links and claim statuses.",
    },
    {
        "stage": 3,
        "name": "Educational simulation",
        "status": "COMPLETE_LOCAL_ONLY",
        "evidence": "Bounded logarithmic display-position simulation.",
    },
    {
        "stage": 4,
        "name": "Tested implementation",
        "status": "VERIFIED_BY_LOCAL_TESTS",
        "evidence": "API, bounds, monotonicity, and UI integration tests.",
    },
    {
        "stage": 5,
        "name": "Validated scientific claim",
        "status": "PENDING_INDEPENDENT_VALIDATION",
        "evidence": (
            "Requires defined physical equations, measurements or accepted data, "
            "and independent scientific review. Not performed."
        ),
    },
)


def snapshot() -> dict[str, Any]:
    return {
        "scope": "EDUCATIONAL_TIMELINE_NOT_LIVE_TELEMETRY",
        "lifecycle": list(LIFECYCLE),
        "epochs": list(EPOCHS),
        "limitations": [
            "Epoch ages are approximate and model-dependent where marked.",
            "The display scale is logarithmic for readability, not a physical law.",
            "No output predicts cosmic fate or validates a universal equilibrium formula.",
            "Independent scientific validation has not been performed.",
        ],
    }


def _validate_position(position: object) -> float:
    if (
        isinstance(position, bool)
        or not isinstance(position, (int, float))
        or not math.isfinite(position)
        or not 0.0 <= position <= 1.0
    ):
        raise ValueError("position must be a finite number between 0 and 1.")
    return float(position)


def simulate_display_position(position: object) -> dict[str, Any]:
    """Map a bounded slider position to an educational log-time display."""
    normalized = _validate_position(position)
    minimum = 1e-36
    maximum = UNIVERSE_AGE_YEARS * SECONDS_PER_YEAR
    log_minimum = math.log10(minimum)
    log_maximum = math.log10(maximum)
    age_seconds = 10 ** (
        log_minimum + normalized * (log_maximum - log_minimum)
    )
    age_years = age_seconds / SECONDS_PER_YEAR

    selected = min(
        EPOCHS,
        key=lambda epoch: abs(
            math.log10(max(cast(float, epoch["age_seconds_min"]), minimum))
            - math.log10(age_seconds)
        ),
    )
    return {
        "scope": "EDUCATIONAL_LOG_TIME_DISPLAY_ONLY",
        "position": normalized,
        "display_age_seconds": age_seconds,
        "display_age_years": age_years,
        "nearest_epoch": selected["id"],
        "nearest_epoch_label": selected["label"],
        "not_a_prediction": True,
    }
