from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def seed_project(target: Path | str = ".") -> None:
    source_root = Path(__file__).resolve().parent
    target_root = Path(target).expanduser().resolve()
    files = [
        Path(".gitignore"),
        Path("README.md"),
        Path("LICENSE"),
        Path("THIRD_PARTY_NOTICES.md"),
        Path("MANIFEST.in"),
        Path("pyproject.toml"),
        Path("seed_project.py"),
        Path("backup_replication.py"),
        *sorted((source_root / "examples" / "demo").glob("*.md")),
        *sorted((source_root / "examples" / "demo").glob("*.json")),
        *sorted((source_root / "src" / "aether_engine").glob("*.py")),
        *sorted((source_root / "tests").glob("test_*.py")),
        *sorted((source_root / ".github" / "workflows").glob("*.yml")),
    ]

    print(f"Seeding Aether Engine project at {target_root}")
    for source in files:
        relative = (
            source.relative_to(source_root)
            if source.is_absolute()
            else source
        )
        destination = target_root / relative
        if destination.exists():
            print(f"  [=] Preserved existing: {relative}")
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_root / relative, destination)
        print(f"  [+] Created: {relative}")
    print("Aether Engine project seed complete.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed a project with the current Aether Engine source and tests."
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=Path.cwd(),
        help="destination directory (default: current directory)",
    )
    args = parser.parse_args(argv)
    seed_project(args.target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
