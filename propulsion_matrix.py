"""Compatibility entry point for the packaged propulsion archive."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from aether_engine.propulsion_matrix import (
    DEFAULT_ARCHIVE_PATH,
    EngineSpecification,
    KineticPropulsionArchive,
    main,
    seed_civilian_references,
    seed_example_engines,
)

__all__ = [
    "DEFAULT_ARCHIVE_PATH",
    "EngineSpecification",
    "KineticPropulsionArchive",
    "seed_civilian_references",
    "seed_example_engines",
]

if __name__ == "__main__":
    main()
