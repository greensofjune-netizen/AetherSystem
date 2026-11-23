"""Reviewed, informational renderings for a small Aether inscription phrasebook."""

from __future__ import annotations

import re
from typing import Any

_SPACE_PATTERN = re.compile(r"\s+")
_PHRASEBOOK = {
    "truth": {
        "latin": "veritas",
        "egyptian_transliteration": "mꜣꜥt",
        "old_babylonian_transliteration": "kīttum",
        "meaning": "truth; truth, justice, and right order in the Egyptian term",
    },
    "peace": {
        "latin": "pax",
        "egyptian_transliteration": "ḥtp",
        "old_babylonian_transliteration": "šulmu",
        "meaning": "peace; wholeness or well-being in the ancient Near Eastern terms",
    },
    "life": {
        "latin": "vita",
        "egyptian_transliteration": "ꜥnḫ",
        "old_babylonian_transliteration": "balāṭu",
        "meaning": "life or living",
    },
    "house": {
        "latin": "domus",
        "egyptian_transliteration": "pr",
        "old_babylonian_transliteration": "bītum",
        "meaning": "house, home, or dwelling",
    },
    "sun": {
        "latin": "sol",
        "egyptian_transliteration": "rꜥ",
        "old_babylonian_transliteration": "šamšu",
        "meaning": "sun",
    },
    "truth and peace": {
        "latin": "veritas et pax",
        "egyptian_transliteration": "mꜣꜥt ḥtp",
        "old_babylonian_transliteration": "kīttum u šulmu",
        "meaning": "truth and peace",
    },
}


def _normalize(text: str) -> str:
    normalized = _SPACE_PATTERN.sub(" ", text.strip().casefold())
    return normalized.rstrip(" .,:;!?")


def render_inscription(text: str) -> dict[str, Any]:
    if not isinstance(text, str):
        raise ValueError("Inscription text must be a string.")
    if not text.strip():
        raise ValueError("Enter text to preview.")
    if len(text) > 240:
        raise ValueError("Inscription preview is limited to 240 characters.")

    entry = _PHRASEBOOK.get(_normalize(text))
    if entry is None:
        return {
            "status": "UNAVAILABLE_NOT_IN_REVIEWED_PHRASEBOOK",
            "exact_original": text,
            "modes": {
                "english": text,
                "latin": None,
                "egyptian_transliteration": None,
                "old_babylonian_transliteration": None,
            },
            "meaning": None,
            "notice": (
                "No reviewed historical rendering is available for this phrase. "
                "The exact English input is preserved; nothing was invented."
            ),
            "command_safe": False,
        }

    return {
        "status": "REVIEWED_APPROXIMATION",
        "exact_original": text,
        "modes": {
            "english": text,
            "latin": entry["latin"],
            "egyptian_transliteration": entry["egyptian_transliteration"],
            "old_babylonian_transliteration": entry[
                "old_babylonian_transliteration"
            ],
        },
        "meaning": entry["meaning"],
        "notice": (
            "Informational transliteration for the supported phrase; variants, "
            "orthography, and grammatical context require scholarly review."
        ),
        "command_safe": False,
    }
