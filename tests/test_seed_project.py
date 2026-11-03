from pathlib import Path

from seed_project import seed_project


def test_seed_project_copies_current_engine_without_overwriting(
    tmp_path: Path,
) -> None:
    target = tmp_path / "new-project"

    seed_project(target)

    assert (target / "pyproject.toml").is_file()
    assert (target / "src/aether_engine/cli.py").is_file()
    assert (target / "src/aether_engine/sanitizer.py").is_file()
    assert (target / "tests/test_sanitizer.py").is_file()
    assert not (target / ".aether-engine.sqlite3").exists()
    assert not (target / ".venv").exists()

    readme = target / "README.md"
    readme.write_text("customized", encoding="utf-8")
    seed_project(target)

    assert readme.read_text(encoding="utf-8") == "customized"
