"""A bounded, in-memory zero-harm branch stewardship simulator."""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass, field
from threading import RLock
from typing import Any

MAX_EQUILIBRIUM_BRANCHES = 512
MAX_COMPOST_RECORDS = 1000
MAX_STEWARDSHIP_LOG_ENTRIES = 1000


class BranchAlreadyRegisteredError(ValueError):
    """Raised when a branch ID is already present in an engine."""


def _utc_timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass
class SystemBranch:
    branch_id: str
    domain: str
    vitality: float
    energy_draw: float
    harm_index: float
    is_stale: bool = False
    last_active_utc: str = field(default_factory=_utc_timestamp)


class SymbioticEquilibriumEngine:
    """Track branches and apply explicit, in-memory stewardship cycles."""

    def __init__(self, vitality_floor: float = 0.25) -> None:
        self._validate_number(vitality_floor, "vitality_floor")
        if not 0 <= vitality_floor <= 1:
            raise ValueError("vitality_floor must be between 0 and 1.")
        self.vitality_floor = float(vitality_floor)
        self.ecosystem: dict[str, SystemBranch] = {}
        self.compost_archive: list[dict[str, Any]] = []
        self.stewardship_log: list[str] = []
        self._lock = RLock()

    @staticmethod
    def _validate_number(value: object, name: str) -> None:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError(f"{name} must be a finite number.")

    @classmethod
    def _validate_branch(cls, branch: SystemBranch) -> None:
        if not isinstance(branch, SystemBranch):
            raise ValueError("branch must be a SystemBranch.")
        for text_value, name, maximum in (
            (branch.branch_id, "branch_id", 100),
            (branch.domain, "domain", 80),
        ):
            if (
                not isinstance(text_value, str)
                or not text_value.strip()
                or len(text_value) > maximum
                or any(ord(character) < 32 for character in text_value)
            ):
                raise ValueError(f"{name} must contain 1-{maximum} characters.")
        for value, name in (
            (branch.vitality, "vitality"),
            (branch.energy_draw, "energy_draw"),
            (branch.harm_index, "harm_index"),
        ):
            cls._validate_number(value, name)
        if not 0 <= branch.vitality <= 1:
            raise ValueError("vitality must be between 0 and 1.")
        if branch.energy_draw < 0:
            raise ValueError("energy_draw must be non-negative.")
        if branch.harm_index < 0:
            raise ValueError("harm_index must be non-negative.")
        if type(branch.is_stale) is not bool:
            raise ValueError("is_stale must be a boolean.")
        if (
            not isinstance(branch.last_active_utc, str)
            or len(branch.last_active_utc) != 20
        ):
            raise ValueError("last_active_utc must use YYYY-MM-DDTHH:MM:SSZ.")
        try:
            time.strptime(branch.last_active_utc, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError as error:
            raise ValueError(
                "last_active_utc must use YYYY-MM-DDTHH:MM:SSZ."
            ) from error

    def _record(self, message: str) -> None:
        self.stewardship_log.append(message)
        del self.stewardship_log[:-MAX_STEWARDSHIP_LOG_ENTRIES]

    def register_branch(self, branch: SystemBranch) -> bool:
        """Admit only valid, zero-harm branches; rejected attempts are logged."""
        self._validate_branch(branch)
        branch_id = branch.branch_id.strip()
        with self._lock:
            if branch.harm_index > 0:
                self._record(
                    f"[BLOCKED] '{branch_id}' rejected at gate: harm_index "
                    f"({branch.harm_index}) > 0.0."
                )
                return False
            if branch_id in self.ecosystem:
                raise BranchAlreadyRegisteredError(
                    f"Branch '{branch_id}' is already registered."
                )
            if len(self.ecosystem) >= MAX_EQUILIBRIUM_BRANCHES:
                raise ValueError(
                    f"No more than {MAX_EQUILIBRIUM_BRANCHES} branches may be registered."
                )
            self.ecosystem[branch_id] = SystemBranch(
                branch_id=branch_id,
                domain=branch.domain.strip(),
                vitality=float(branch.vitality),
                energy_draw=float(branch.energy_draw),
                harm_index=float(branch.harm_index),
                is_stale=branch.is_stale,
                last_active_utc=branch.last_active_utc,
            )
            self._record(
                f"[ADMITTED] '{branch_id}' ({branch.domain.strip()}) integrated "
                "into equilibrium."
            )
        return True

    def nurture_and_advance(self, boost_amount: float = 0.08) -> list[str]:
        """Raise vitality on active harmless branches by a bounded boost."""
        self._validate_number(boost_amount, "boost_amount")
        if not 0 <= boost_amount <= 1:
            raise ValueError("boost_amount must be between 0 and 1.")
        with self._lock:
            active = [
                branch
                for branch in self.ecosystem.values()
                if branch.harm_index == 0 and not branch.is_stale
            ]
            if not active:
                return ["No active branches available to nurture."]

            average_vitality = sum(branch.vitality for branch in active) / len(active)
            notes: list[str] = []
            for branch in active:
                support = boost_amount * (
                    1.2 if branch.vitality < average_vitality else 0.8
                )
                branch.vitality = min(1.0, round(branch.vitality + support, 3))
                branch.last_active_utc = _utc_timestamp()
                notes.append(
                    f"[ADVANCE] '{branch.branch_id}' ({branch.domain}) -> Vitality: "
                    f"{branch.vitality:.1%}"
                )
            for note in notes:
                self._record(note)
            return notes

    def prune_and_compost(self) -> list[str]:
        """Remove harmful, stale, or below-floor branches from this simulator."""
        with self._lock:
            candidates = [
                (
                    branch_id,
                    branch,
                    "Harm invariant violated"
                    if branch.harm_index > 0
                    else "Dead weight / vitality below threshold",
                )
                for branch_id, branch in self.ecosystem.items()
                if branch.harm_index > 0
                or branch.is_stale
                or branch.vitality < self.vitality_floor
            ]
            notes: list[str] = []
            for branch_id, branch, reason in candidates:
                del self.ecosystem[branch_id]
                if branch.harm_index == 0:
                    self.compost_archive.append(
                        {
                            "recycled_id": branch.branch_id,
                            "domain": branch.domain,
                            "reason": reason,
                            "recycled_utc": _utc_timestamp(),
                        }
                    )
                    del self.compost_archive[:-MAX_COMPOST_RECORDS]
                notes.append(
                    f"[PRUNED] '{branch_id}' ({reason}) -> Freed "
                    f"{branch.energy_draw:g} energy units from the in-memory simulation."
                )
            for note in notes:
                self._record(note)
            return notes

    def system_health_report(self) -> dict[str, Any]:
        with self._lock:
            branches = list(self.ecosystem.values())
            average_vitality = (
                round(sum(branch.vitality for branch in branches) / len(branches), 3)
                if branches
                else 0.0
            )
            return {
                "active_branches": sum(
                    not branch.is_stale and branch.harm_index == 0
                    for branch in branches
                ),
                "registered_branches": len(branches),
                "average_vitality": average_vitality,
                "composted_count": len(self.compost_archive),
                "zero_harm_verified": all(
                    branch.harm_index == 0 for branch in branches
                ),
                "vitality_floor": self.vitality_floor,
                "branches": [
                    {
                        "branch_id": branch.branch_id,
                        "domain": branch.domain,
                        "vitality": branch.vitality,
                        "energy_draw": branch.energy_draw,
                        "harm_index": branch.harm_index,
                        "is_stale": branch.is_stale,
                        "last_active_utc": branch.last_active_utc,
                    }
                    for branch in sorted(branches, key=lambda item: item.branch_id)
                ],
                "compost_archive": [dict(item) for item in self.compost_archive],
                "stewardship_log": self.stewardship_log[-100:],
            }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cycle",
        choices=("demo", "report", "nurture", "prune"),
        default="demo",
        help="Run an in-memory stewardship cycle, then print its JSON snapshot.",
    )
    args = parser.parse_args(argv)
    engine = SymbioticEquilibriumEngine()
    for branch in (
        SystemBranch("forest_canopy_sync", "Atmosphere", 0.72, 0.4, 0.0),
        SystemBranch("ocean_current_ledger", "Ocean", 0.64, 0.5, 0.0),
        SystemBranch("ancestral_stone_archive", "Archive", 0.85, 0.2, 0.0),
        SystemBranch(
            "legacy_bloated_loop", "Archive", 0.12, 1.4, 0.0, is_stale=True
        ),
    ):
        engine.register_branch(branch)
    engine.register_branch(
        SystemBranch("extractive_strip_miner", "Kinetics", 0.9, 2.0, 0.8)
    )
    notes: list[str] = []
    if args.cycle in {"demo", "prune"}:
        notes.extend(engine.prune_and_compost())
    if args.cycle in {"demo", "nurture"}:
        notes.extend(engine.nurture_and_advance())
    print(
        json.dumps(
            {
                "cycle": args.cycle,
                "cycle_notes": notes,
                "snapshot": engine.system_health_report(),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
