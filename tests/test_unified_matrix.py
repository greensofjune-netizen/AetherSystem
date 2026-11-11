import re
import sqlite3
from pathlib import Path

import pytest

from history_matrix_archive import UnifiedArtifact, UnifiedMatrixCoreEngine


def artifact(
    matrix_id: str,
    *,
    domain: str = "Astronomy",
    title: str | None = None,
) -> UnifiedArtifact:
    return UnifiedArtifact(
        matrix_id=matrix_id,
        title=title or f"Example {matrix_id}",
        domain=domain,
        origin_era="Example era",
        technical_payload='{"sample": true}',
        ethical_clearance="Example data; not independently verified.",
    )


def test_vault_upserts_and_filters_domain(tmp_path: Path):
    engine = UnifiedMatrixCoreEngine(tmp_path / "unified.sqlite3")
    engine.secure_vault_entry(artifact("ASTRO_02"))
    engine.secure_vault_entry(artifact("ASTRO_01"))
    engine.secure_vault_entry(artifact("HISTORY_01", domain="History"))

    records = engine.pull_domain_matrix("Astronomy")
    assert [record["matrix_id"] for record in records] == ["ASTRO_01", "ASTRO_02"]
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", records[0]["last_sync_utc"])
    assert engine.pull_domain_matrix("' OR 1=1 --") == []

    engine.secure_vault_entry(artifact("ASTRO_01", title="Updated astronomy record"))
    updated = engine.pull_domain_matrix("Astronomy")[0]
    assert updated["title"] == "Updated astronomy record"
    assert updated["technical_payload"] == '{"sample": true}'


def test_crosslinks_require_existing_artifacts_and_keep_first_rationale(tmp_path: Path):
    engine = UnifiedMatrixCoreEngine(tmp_path / "unified.sqlite3")
    engine.secure_vault_entry(artifact("SOURCE"))
    engine.secure_vault_entry(artifact("TARGET", domain="Engineering"))
    engine.inject_crosslink("SOURCE", "TARGET", "Initial rationale.")
    engine.inject_crosslink("SOURCE", "TARGET", "Replacement rationale.")

    with sqlite3.connect(engine.db_path) as connection:
        assert connection.execute(
            "SELECT link_rationale FROM unified_system_crosslinks"
        ).fetchone() == ("Initial rationale.",)

    with pytest.raises(sqlite3.IntegrityError):
        engine.inject_crosslink("MISSING", "TARGET", "Invalid link.")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("matrix_id", " ", "matrix_id"),
        ("technical_payload", "", "technical_payload"),
        ("ethical_clearance", None, "ethical_clearance"),
    ],
)
def test_vault_rejects_invalid_artifact_fields(
    tmp_path: Path, field: str, value: str | None, message: str
):
    item = artifact("VALID")
    setattr(item, field, value)
    engine = UnifiedMatrixCoreEngine(tmp_path / "unified.sqlite3")

    with pytest.raises(ValueError, match=message):
        engine.secure_vault_entry(item)


def test_link_and_domain_inputs_are_validated(tmp_path: Path):
    engine = UnifiedMatrixCoreEngine(tmp_path / "unified.sqlite3")
    with pytest.raises(ValueError, match="Crosslink IDs"):
        engine.inject_crosslink(" ", "TARGET", "Rationale.")
    with pytest.raises(ValueError, match="domain"):
        engine.pull_domain_matrix("")
