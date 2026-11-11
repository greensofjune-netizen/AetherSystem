import sys

import pytest

import build_app
import build_galileo


@pytest.mark.parametrize("script", [build_app, build_galileo])
def test_build_script_help_does_not_start_build(script, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", [script.__file__, "--help"])

    with pytest.raises(SystemExit) as error:
        script.main()

    assert error.value.code == 0
    assert "usage:" in capsys.readouterr().out.lower()


def test_galileo_build_does_not_overwrite_existing_app(tmp_path, monkeypatch, capsys):
    existing = tmp_path / "Galileo.app"
    existing.mkdir()
    marker = existing / "keep"
    marker.write_text("existing")
    monkeypatch.setattr(sys, "argv", ["build_galileo.py", "--output-dir", str(tmp_path)])
    monkeypatch.setattr(sys, "platform", "darwin")

    assert build_galileo.main() == 1
    assert marker.read_text() == "existing"
    assert "Refusing to overwrite" in capsys.readouterr().err


def test_aristotle_build_help_names_app(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["build_aristotle.py", "--help"])

    with pytest.raises(SystemExit) as error:
        build_galileo.main(aristotle=True)

    assert error.value.code == 0
    assert "new Matrix Aristotle.app" in capsys.readouterr().out


def test_portable_launcher_does_not_embed_build_project(tmp_path):
    source = build_galileo.launcher_source(tmp_path, "aristotle_desktop", portable=True)
    assert str(tmp_path) not in source
    assert "'AetherSystem' / 'Matrix'" in source
    local = build_galileo.launcher_source(tmp_path, "aristotle_desktop", portable=False)
    assert str(tmp_path) in local
