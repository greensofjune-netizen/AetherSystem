import math

import pytest

from food_matrix_streamer import (
    export_edible_star_gcode,
    generate_edible_star_gcode,
    main,
)


def test_generated_template_has_six_fold_geometry_and_no_homing():
    commands = generate_edible_star_gcode(layers=1, steps_per_revolution=36)

    assert commands[:5] == [
        "; AetherSystem six-fold paste path; export-only generic template",
        "; Not validated for a printer, firmware, workspace, ingredient, or hygiene process",
        "G21 ; Use millimeters",
        "G90 ; Absolute X/Y/Z positioning",
        "M83 ; Relative extrusion; verify firmware support before use",
    ]
    assert not any(command.startswith("G28") for command in commands)
    assert len([command for command in commands if command.startswith("G1 X")]) == 37

    points = []
    for command in commands:
        if command.startswith("G1 X"):
            fields = {
                part[0]: part[1:]
                for part in command.split()[1:]
                if part[0] in "XY"
            }
            points.append((float(fields["X"]), float(fields["Y"])))
    center_x = 100.0
    center_y = 100.0
    radial_distances = [
        math.hypot(x - center_x, y - center_y) for x, y in points[:36]
    ]
    assert radial_distances[0] == pytest.approx(radial_distances[6], abs=0.001)
    assert radial_distances[3] == pytest.approx(radial_distances[9], abs=0.001)
    assert all(" E" in command for command in commands[6:])
    assert points[0] == points[-1]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"layers": True}, "layers must be an integer"),
        ({"layers": 0}, "layers must be between"),
        ({"layers": 101}, "layers must be between"),
        ({"radius_mm": float("nan")}, "radius_mm must be a finite number"),
        ({"radius_mm": 0}, "radius_mm must be between"),
        ({"layer_height": float("inf")}, "layer_height must be a finite number"),
        ({"steps_per_revolution": 35}, "multiple of 6"),
        ({"steps_per_revolution": 500}, "multiple of 6"),
        ({"extrusion_per_mm": -0.1}, "extrusion_per_mm must be between"),
    ],
)
def test_generator_rejects_invalid_parameters(kwargs, message):
    with pytest.raises(ValueError, match=message):
        generate_edible_star_gcode(**kwargs)


def test_export_writes_ascii_gcode_without_hardware_connection(tmp_path):
    output = tmp_path / "star.gcode"

    line_count = export_edible_star_gcode(output, layers=2)

    contents = output.read_text(encoding="ascii")
    assert line_count == len(contents.splitlines())
    assert contents.endswith("\n")
    assert sum(line.startswith("G1 Z") for line in contents.splitlines()) == 1
    assert "export-only" in contents


def test_export_does_not_overwrite_an_existing_file(tmp_path):
    output = tmp_path / "existing.gcode"
    output.write_text("keep this file", encoding="ascii")

    with pytest.raises(FileExistsError):
        export_edible_star_gcode(output, layers=1)

    assert output.read_text(encoding="ascii") == "keep this file"


def test_cli_requires_explicit_output_and_exports(tmp_path):
    output = tmp_path / "copernicus-star.gcode"

    with pytest.raises(SystemExit) as error:
        main(["--layers", "1"])
    assert error.value.code == 2

    assert main(["--output", str(output), "--layers", "1"]) == 0
    assert output.exists()
