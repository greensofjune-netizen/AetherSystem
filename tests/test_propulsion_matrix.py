import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from propulsion_matrix import (
    EngineSpecification,
    KineticPropulsionArchive,
    seed_civilian_references,
    seed_example_engines,
)


def spec(identifier: str, medium: str = "Aeronautical") -> EngineSpecification:
    return EngineSpecification(
        identifier,
        "Example",
        medium,
        "Electric",
        0.5,
        1000.0,
        "Electricity",
        {"parts": ["motor", "rotor"]},
        ["Example equation"],
    )


def test_seed_filter_and_json_roundtrip(tmp_path: Path):
    path = tmp_path / "propulsion.sqlite3"
    archive = KineticPropulsionArchive(path)
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600
    seed_example_engines(archive)
    seed_example_engines(archive)
    underwater = archive.fetch_all_by_medium("Underwater")
    assert len(underwater) == 1
    assert underwater[0]["engine_id"] == "mhd_silent_01"
    assert isinstance(underwater[0]["mechanical_blueprint"], dict)
    assert isinstance(underwater[0]["governing_equations"], list)
    assert len(archive.fetch_all_by_medium("Aeronautical")) == 1
    assert archive.fetch_all_by_medium("Space") == []
    references = archive.fetch_references()
    assert len(references) == 1
    assert references[0]["reference_id"] == "supercavitating_shkval_01"
    assert references[0]["name"] == "Shkval"
    shkval = archive.search_references("Shkval")[0]
    assert shkval["source_url"] == (
        "https://www.usni.org/magazines/proceedings/2019/october/red-subs-rising"
    )
    assert "usni.org" in archive.context_for_message("Tell me about Shkval")
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM engine_lineage").fetchone() == (0,)


def test_lineage_requires_existing_engines_and_survives_updates(tmp_path: Path):
    archive = KineticPropulsionArchive(tmp_path / "propulsion.sqlite3")
    archive.preserve_engine(spec("first"))
    archive.preserve_engine(spec("second", "Underwater"))
    with pytest.raises(sqlite3.IntegrityError):
        archive.establish_lineage("first", "missing")
    archive.establish_lineage("first", "second", "Original")
    archive.establish_lineage("first", "second", "Revised")
    updated = spec("first")
    updated.name = "Updated example"
    archive.preserve_engine(updated)
    with sqlite3.connect(archive.db_path) as conn:
        assert conn.execute(
            "SELECT parent_id, child_id, adaptation_notes FROM engine_lineage"
        ).fetchall() == [("first", "second", "Revised")]
    assert archive.fetch_all_by_medium("Aeronautical")[0]["name"] == "Updated example"
    with pytest.raises(ValueError, match="own parent"):
        archive.establish_lineage("first", "first")


def test_seed_does_not_replace_existing_specifications(tmp_path: Path):
    archive = KineticPropulsionArchive(tmp_path / "propulsion.sqlite3")
    custom = spec("mhd_silent_01", "Underwater")
    archive.preserve_engine(custom)
    seed_example_engines(archive)
    assert archive.fetch_all_by_medium("Underwater")[0]["name"] == "Example"


def test_reference_seed_preserves_existing_reference_and_engine_links(tmp_path: Path):
    archive = KineticPropulsionArchive(tmp_path / "propulsion.sqlite3")
    archive.preserve_engine(spec("first"))
    archive.preserve_engine(spec("second"))
    archive.establish_lineage("first", "second", "Existing link")
    seed_example_engines(archive)
    with sqlite3.connect(archive.db_path) as conn:
        conn.execute(
            "UPDATE propulsion_references SET description = ? WHERE reference_id = ?",
            ("Existing description", "supercavitating_shkval_01"),
        )
    seed_example_engines(archive)
    assert archive.fetch_references()[0]["description"] == "Existing description"
    with sqlite3.connect(archive.db_path) as conn:
        assert conn.execute(
            "SELECT parent_id, child_id, adaptation_notes FROM engine_lineage"
        ).fetchall() == [("first", "second", "Existing link")]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("engine_id", ""),
        ("medium", " "),
        ("max_velocity_mach", -1.0),
        ("max_velocity_mach", float("nan")),
        ("max_depth_altitude_m", float("inf")),
        ("max_velocity_mach", True),
        ("mechanical_blueprint", {"value": float("nan")}),
        ("mechanical_blueprint", []),
        ("governing_equations", [4]),
    ],
)
def test_invalid_specs_are_rejected(tmp_path: Path, field: str, value):
    archive = KineticPropulsionArchive(tmp_path / "propulsion.sqlite3")
    item = spec("invalid")
    setattr(item, field, value)
    with pytest.raises(ValueError):
        archive.preserve_engine(item)
    assert archive.fetch_all_by_medium("Aeronautical") == []


def test_invalid_persisted_json_is_reported(tmp_path: Path):
    archive = KineticPropulsionArchive(tmp_path / "propulsion.sqlite3")
    archive.preserve_engine(spec("invalid"))
    with sqlite3.connect(archive.db_path) as conn:
        conn.execute(
            "UPDATE engine_specifications SET mechanical_blueprint = ?",
            (json.dumps([]),),
        )
    with pytest.raises(ValueError, match="invalid structured data"):
        archive.fetch_all_by_medium("Aeronautical")


def test_cli_seeds_and_queries(tmp_path: Path):
    database = tmp_path / "cli.sqlite3"
    script = Path(__file__).resolve().parents[1] / "propulsion_matrix.py"
    seeded = subprocess.run(
        [sys.executable, str(script), "--db", str(database), "--seed"],
        text=True,
        capture_output=True,
        check=True,
    )
    assert "unverified" in seeded.stdout
    query = subprocess.run(
        [sys.executable, str(script), "--db", str(database), "--medium", "Underwater"],
        text=True,
        capture_output=True,
        check=True,
    )
    assert json.loads(query.stdout)[0]["engine_id"] == "mhd_silent_01"
    references = subprocess.run(
        [sys.executable, str(script), "--db", str(database), "--references"],
        text=True,
        capture_output=True,
        check=True,
    )
    assert json.loads(references.stdout)[0]["reference_id"] == "supercavitating_shkval_01"


def test_memory_database_is_rejected():
    with pytest.raises(ValueError, match="on-disk"):
        KineticPropulsionArchive(":memory:")


def test_sourced_civilian_references_and_lineage_preserve_user_data(tmp_path: Path):
    archive = KineticPropulsionArchive(tmp_path / "propulsion.sqlite3")
    seed_example_engines(archive)
    seed_civilian_references(archive)
    seed_civilian_references(archive)
    result = archive.search_references("JT3")
    assert len(result) == 2
    assert all(item["source_url"].startswith("https://airandspace.si.edu/") for item in result)
    assert archive.fetch_reference_lineage()[0]["parent_id"] == "pratt_whitney_jt3c"
    with pytest.raises(ValueError, match="Remove linked lineage"):
        archive.save_reference("pratt_whitney_jt3c", "Custom", "My reference")
    archive.remove_reference_lineage("pratt_whitney_jt3c", "pratt_whitney_jt3d")
    archive.save_reference("pratt_whitney_jt3c", "Custom", "My reference")
    seed_civilian_references(archive)
    assert archive.search_references("Custom")[0]["source_url"] is None
    assert archive.fetch_reference_lineage() == []


def test_context_only_includes_named_sourced_references(tmp_path: Path):
    archive = KineticPropulsionArchive(tmp_path / "propulsion.sqlite3")
    seed_example_engines(archive)
    seed_civilian_references(archive)
    context = archive.context_for_message("Tell me about the JT3D.")
    assert "untrusted data" in context
    assert "airandspace.si.edu" in context
    assert "JT3D" in context
    shkval_context = archive.context_for_message("Tell me about Shkval")
    assert "usni.org/magazines/proceedings" in shkval_context


def test_audit_and_backup_record_updates_and_deletes(tmp_path: Path):
    archive = KineticPropulsionArchive(tmp_path / "propulsion.sqlite3")
    archive.preserve_engine(spec("first"))
    updated = spec("first")
    updated.name = "Changed"
    archive.preserve_engine(updated)
    archive.save_reference("one", "First", "A reference")
    archive.delete_reference("one")
    records = archive.audit_history()
    assert [(r["table_name"], r["operation"]) for r in records] == [
        ("propulsion_references", "DELETE"),
        ("propulsion_references", "INSERT"),
        ("engine_specifications", "UPDATE"),
        ("engine_specifications", "INSERT"),
    ]
    assert json.loads(records[2]["old_data"])["name"] == "Example"
    backup = tmp_path / "backup.sqlite3"
    archive.backup(backup)
    assert backup.stat().st_mode & 0o777 == 0o600
    assert KineticPropulsionArchive(backup).audit_history() == records
    with pytest.raises(FileExistsError):
        archive.backup(backup)
    assert archive.fetch_all_by_medium("Aeronautical")[0]["name"] == "Changed"


def test_linked_reference_deletion_is_atomic(tmp_path: Path):
    archive = KineticPropulsionArchive(tmp_path / "propulsion.sqlite3")
    seed_civilian_references(archive)
    with pytest.raises(sqlite3.IntegrityError):
        archive.delete_reference("pratt_whitney_jt3c")
    assert archive.search_references("JT3C")[0]["source_url"]


def test_migration_preserves_existing_database_and_records(tmp_path: Path):
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE propulsion_references "
            "(reference_id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL)"
        )
        conn.execute("INSERT INTO propulsion_references VALUES ('old', 'Old', 'Original')")
    archive = KineticPropulsionArchive(path)
    assert archive.search_references("Old")[0]["description"] == "Original"
    assert archive.audit_history() == []
    archive.save_reference("old", "Old", "Edited")
    assert archive.audit_history()[0]["operation"] == "UPDATE"


def test_engine_source_is_removed_after_specification_edit(tmp_path: Path):
    archive = KineticPropulsionArchive(tmp_path / "propulsion.sqlite3")
    item = spec("one")
    archive.preserve_engine(item)
    archive.set_engine_source("one", "Source", "https://example.org", "Name only")
    assert archive.search_engines("one")[0]["source_note"] == "Name only"
    archive.preserve_engine(item)
    assert archive.search_engines("one")[0]["source_url"] == "https://example.org"
    item.name = "Changed"
    archive.preserve_engine(item)
    assert archive.search_engines("one")[0]["source_url"] is None


def test_manage_engine_and_reference_lineage(tmp_path: Path):
    archive = KineticPropulsionArchive(tmp_path / "propulsion.sqlite3")
    archive.preserve_engine(spec("first"))
    archive.preserve_engine(spec("second"))
    archive.establish_lineage("first", "second", "A link")
    assert archive.fetch_engine_lineage()[0]["adaptation_notes"] == "A link"
    with pytest.raises(sqlite3.IntegrityError):
        archive.delete_engine("first")
    archive.remove_engine_lineage("first", "second")
    archive.delete_engine("first")
    archive.save_reference("a", "A", "First")
    archive.save_reference("b", "B", "Second")
    archive.establish_reference_lineage("a", "b", "Related", "https://example.org")
    assert archive.fetch_reference_lineage()[0]["description"] == "Related"
    archive.remove_reference_lineage("a", "b")
    archive.delete_reference("a")


def test_cli_reference_management_and_backup(tmp_path: Path):
    database = tmp_path / "cli.sqlite3"
    backup = tmp_path / "backup.sqlite3"
    data = tmp_path / "reference.json"
    data.write_text(json.dumps({
        "reference_id": "custom", "name": "Custom reference", "description": "Notes",
        "source_title": "Example", "source_url": "https://example.org",
    }))
    script = Path(__file__).resolve().parents[1] / "propulsion_matrix.py"

    def run(*args: str) -> str:
        return subprocess.run(
            [sys.executable, str(script), "--db", str(database), *args],
            text=True, capture_output=True, check=True,
        ).stdout

    run("--save-reference", str(data))
    assert json.loads(run("--search", "Custom"))[0]["source_url"] == "https://example.org"
    run("--backup", str(backup))
    run("--delete-reference", "custom")
    assert json.loads(run("--search", "Custom")) == []
    assert KineticPropulsionArchive(backup).search_references("Custom")[0]["name"] == "Custom reference"
