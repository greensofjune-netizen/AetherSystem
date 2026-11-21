import json
import os
import subprocess
import sys
import tarfile
import venv
from email.parser import Parser
from pathlib import Path
from zipfile import ZipFile


def test_distribution_is_licensed_and_core_runs_without_extras(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "dist"
    subprocess.run(
        [sys.executable, "-m", "build", "--outdir", str(output)],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    source = next(output.glob("*.tar.gz"))
    wheel = next(output.glob("*.whl"))
    with tarfile.open(source) as archive:
        prefix = source.name.removesuffix(".tar.gz") + "/"
        names = [name.removeprefix(prefix) for name in archive.getnames()]
        assert "LICENSE" in names
        assert "THIRD_PARTY_NOTICES.md" in names
        assert "examples/demo/sample-project.json" in names
        assert {
            "aether_metrics.json",
            "historian_telemetry_vault.json",
            "ingested_knowledge.txt",
        }.isdisjoint(names)
        assert not any(
            name.startswith((".agents/", ".build/", ".venv/", "backups/", "models/"))
            or ".sqlite" in name
            or name.endswith((".pkg", ".gguf", ".log", ".jsonl", ".pyc"))
            for name in names
        )
        sample_file = archive.extractfile(prefix + "examples/demo/sample-project.json")
        assert sample_file is not None
        sample = tmp_path / "sample-project.json"
        sample.write_bytes(sample_file.read())

    with ZipFile(wheel) as archive:
        names = archive.namelist()
        assert "food_matrix_streamer.py" in names
        assert "equilibrium_peer_review.py" in names
        assert "aether_engine/equilibrium_decision.py" in names
        assert not any(
            ".sqlite" in name
            or name.endswith((".pkg", ".gguf", ".log", ".jsonl", ".pyc"))
            for name in names
        )
        metadata_path = next(name for name in names if name.endswith("/METADATA"))
        entry_points_path = next(
            name for name in names if name.endswith("/entry_points.txt")
        )
        entry_points = archive.read(entry_points_path).decode("utf-8")
        assert (
            "aether-equilibrium-review = "
            "aether_engine.equilibrium_decision:main"
        ) in entry_points
        assert (
            "aether-equilibrium-weights = "
            "equilibrium_peer_review:main"
        ) in entry_points
        for asset in ("index.html", "monitor_tasks.js", "aether_client.js"):
            asset_path = next(
                name for name in names
                if name.endswith(f"/share/aether-engine/frontend/{asset}")
            )
            assert archive.read(asset_path) == (root / "frontend" / asset).read_bytes()
        for asset in (
            "index.html", "tasks.css", "manifest.webmanifest",
            "icon.svg", "icon-192.png", "icon-512.png",
        ):
            asset_path = next(
                name for name in names
                if name.endswith(f"/share/aether-engine/frontend/tasks/{asset}")
            )
            assert archive.read(asset_path) == (root / "frontend" / "tasks" / asset).read_bytes()
        for asset in (
            "weather.html", "weather.css", "weather.js", "copernicus.js",
            "persona_matrix.js", "persona_matrix.css", "stargazer.html",
            "stargazer.css", "stargazer.js", "astronomy.css", "speech.js",
        ):
            asset_path = next(
                name for name in names
                if name.endswith(f"/share/aether-engine/observatory/{asset}")
            )
            assert archive.read(asset_path) == (root / "frontend" / asset).read_bytes()
        assert "aether_engine/master_desktop.py" in names
        metadata = Parser().parsestr(archive.read(metadata_path).decode("utf-8"))
        assert metadata["License-Expression"] == "MIT"
        assert metadata.get_all("License-File") == ["LICENSE"]
        license_path = next(
            name for name in names if name.endswith(".dist-info/licenses/LICENSE")
        )
        assert archive.read(license_path) == (root / "LICENSE").read_bytes()

    environment = tmp_path / "venv"
    venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    process_env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"}
    }
    subprocess.run(
        [str(python), "-m", "pip", "install", "--no-deps", "--no-index", str(wheel)],
        cwd=tmp_path,
        env=process_env,
        check=True,
        capture_output=True,
        text=True,
    )

    food_cli = environment / (
        "Scripts/aether-food-gcode.exe"
        if os.name == "nt"
        else "bin/aether-food-gcode"
    )
    result = subprocess.run(
        [str(food_cli), "--help"],
        cwd=tmp_path,
        env=process_env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "--steps-per-revolution" in result.stdout

    equilibrium_cli = environment / (
        "Scripts/aether-equilibrium-review.exe"
        if os.name == "nt"
        else "bin/aether-equilibrium-review"
    )
    result = subprocess.run(
        [
            str(equilibrium_cli),
            "--action-name",
            "Packaging check",
            "--target-impact-severity",
            "20",
            "--ecosystem-hazard",
            "5",
        ],
        cwd=tmp_path,
        env=process_env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    equilibrium = json.loads(result.stdout)
    assert equilibrium["decision"] == "SIMULATION_ONLY"
    assert equilibrium["action_executed"] is False

    weights_cli = environment / (
        "Scripts/aether-equilibrium-weights.exe"
        if os.name == "nt"
        else "bin/aether-equilibrium-weights"
    )
    result = subprocess.run(
        [str(weights_cli)],
        cwd=tmp_path,
        env=process_env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "Risk Input: 0.15" in result.stdout
    assert "Risk Input: 0.50" in result.stdout
    assert "Risk Input: 0.85" in result.stdout
    assert "does not prove physical wave-particle duality" in result.stdout

    def cli(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(python), "-m", "aether_engine", *arguments],
            cwd=tmp_path,
            env=process_env,
            capture_output=True,
            text=True,
        )

    result = cli("--help")
    assert result.returncode == 0, result.stderr
    assert "Track project tasks" in result.stdout
    result = cli("task", "add", "Installed wheel task")
    assert result.returncode == 0, result.stderr
    result = cli("event", "add", "Installed wheel event", "--topic", "test")
    assert result.returncode == 0, result.stderr
    result = cli("export")
    assert result.returncode == 0, result.stderr
    exported = json.loads(result.stdout)
    assert exported["tasks"][0]["title"] == "Installed wheel task"
    assert exported["events"][0]["message"] == "Installed wheel event"

    demo_args = ("--database", str(tmp_path / "demo.sqlite3"))
    result = cli(*demo_args, "restore", str(sample))
    assert result.returncode == 0, result.stderr
    result = cli(*demo_args, "status")
    assert result.returncode == 0, result.stderr
    assert "2 open   2 done   4 total" in result.stdout
    result = cli(*demo_args, "restore", str(sample))
    assert result.returncode == 1
    assert "Database is not empty" in result.stderr
    result = cli(*demo_args, "export")
    assert result.returncode == 0, result.stderr
    demo = json.loads(result.stdout)
    original = json.loads(sample.read_text(encoding="utf-8"))
    assert demo["tasks"] == original["tasks"]
    assert demo["events"] == original["events"]
