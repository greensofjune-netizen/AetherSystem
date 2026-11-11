"""Launch the unified Matrix Aristotle desktop companion."""

from pathlib import Path

from .galileo_desktop import main as desktop_main


def main(*, project_directory: Path | None = None) -> int:
    return desktop_main(project_directory=project_directory, aristotle=True)


if __name__ == "__main__":
    raise SystemExit(main())
