"""Generate and export a six-fold paste-extrusion G-code template.

This module never connects to a printer. Its output is a generic template,
not a validated or food-safety-certified print job.
"""

import argparse
import math
from pathlib import Path
from typing import Sequence

MAX_LAYERS = 100
MAX_RADIUS_MM = 500.0
MAX_STEPS_PER_REVOLUTION = 360
MAX_COORDINATE_MM = 1000.0


def _finite_number(
    name: str,
    value: int | float,
    *,
    minimum: float,
    maximum: float,
) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ValueError(f"{name} must be a finite number.")
    number = float(value)
    if not minimum <= number <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return number


def generate_edible_star_gcode(
    layers: int = 8,
    radius_mm: float = 25.0,
    layer_height: float = 1.2,
    *,
    center_x_mm: float = 100.0,
    center_y_mm: float = 100.0,
    steps_per_revolution: int = 36,
    extrusion_per_mm: float = 0.045,
) -> list[str]:
    """Generate an export-only six-fold star path with relative extrusion."""
    if isinstance(layers, bool) or not isinstance(layers, int):
        raise ValueError("layers must be an integer.")
    if not 1 <= layers <= MAX_LAYERS:
        raise ValueError(f"layers must be between 1 and {MAX_LAYERS}.")
    if (
        isinstance(steps_per_revolution, bool)
        or not isinstance(steps_per_revolution, int)
        or not 12 <= steps_per_revolution <= MAX_STEPS_PER_REVOLUTION
        or steps_per_revolution % 6 != 0
    ):
        raise ValueError(
            "steps_per_revolution must be a multiple of 6 between 12 and "
            f"{MAX_STEPS_PER_REVOLUTION}."
        )

    radius = _finite_number(
        "radius_mm", radius_mm, minimum=0.1, maximum=MAX_RADIUS_MM
    )
    height = _finite_number("layer_height", layer_height, minimum=0.1, maximum=10.0)
    center_x = _finite_number(
        "center_x_mm",
        center_x_mm,
        minimum=-MAX_COORDINATE_MM,
        maximum=MAX_COORDINATE_MM,
    )
    center_y = _finite_number(
        "center_y_mm",
        center_y_mm,
        minimum=-MAX_COORDINATE_MM,
        maximum=MAX_COORDINATE_MM,
    )
    rate = _finite_number(
        "extrusion_per_mm", extrusion_per_mm, minimum=0.000001, maximum=1.0
    )

    gcode = [
        "; AetherSystem six-fold paste path; export-only generic template",
        "; Not validated for a printer, firmware, workspace, ingredient, or hygiene process",
        "G21 ; Use millimeters",
        "G90 ; Absolute X/Y/Z positioning",
        "M83 ; Relative extrusion; verify firmware support before use",
    ]

    previous_x: float | None = None
    previous_y: float | None = None
    for layer in range(1, layers + 1):
        z = round(layer * height, 2)
        if previous_x is None or previous_y is None:
            theta = 0.0
            start_radius = radius * (1.0 + 0.15 * math.sin(6.0 * theta))
            previous_x = round(center_x + start_radius, 2)
            previous_y = round(center_y, 2)
            gcode.append(
                f"G1 X{previous_x:.2f} Y{previous_y:.2f} Z{z:.2f} F600"
            )
        else:
            gcode.append(f"G1 Z{z:.2f} F400")

        for step in range(1, steps_per_revolution + 1):
            theta = (2.0 * math.pi * step) / steps_per_revolution
            current_radius = radius * (1.0 + 0.15 * math.sin(6.0 * theta))
            x = round(center_x + current_radius * math.cos(theta), 2)
            y = round(center_y + current_radius * math.sin(theta), 2)
            segment_length = math.hypot(x - previous_x, y - previous_y)
            extrusion = round(rate * segment_length, 6)
            gcode.append(
                f"G1 X{x:.2f} Y{y:.2f} E{extrusion:.6f} F900"
            )
            previous_x = x
            previous_y = y

    return gcode


def export_edible_star_gcode(
    output_path: str | Path,
    *,
    layers: int = 8,
    radius_mm: float = 25.0,
    layer_height: float = 1.2,
    center_x_mm: float = 100.0,
    center_y_mm: float = 100.0,
    steps_per_revolution: int = 36,
    extrusion_per_mm: float = 0.045,
) -> int:
    """Write a generated G-code template and return its line count."""
    commands = generate_edible_star_gcode(
        layers=layers,
        radius_mm=radius_mm,
        layer_height=layer_height,
        center_x_mm=center_x_mm,
        center_y_mm=center_y_mm,
        steps_per_revolution=steps_per_revolution,
        extrusion_per_mm=extrusion_per_mm,
    )
    with Path(output_path).open("x", encoding="ascii", newline="\n") as output:
        output.write("\n".join(commands) + "\n")
    return len(commands)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export a generic six-fold paste-path G-code template."
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="destination .gcode file; no printer connection is opened",
    )
    parser.add_argument("--layers", type=int, default=8)
    parser.add_argument("--radius-mm", type=float, default=25.0)
    parser.add_argument("--layer-height-mm", type=float, default=1.2)
    parser.add_argument("--center-x-mm", type=float, default=100.0)
    parser.add_argument("--center-y-mm", type=float, default=100.0)
    parser.add_argument("--steps-per-revolution", type=int, default=36)
    parser.add_argument("--extrusion-per-mm", type=float, default=0.045)
    args = parser.parse_args(argv)

    line_count = export_edible_star_gcode(
        args.output,
        layers=args.layers,
        radius_mm=args.radius_mm,
        layer_height=args.layer_height_mm,
        center_x_mm=args.center_x_mm,
        center_y_mm=args.center_y_mm,
        steps_per_revolution=args.steps_per_revolution,
        extrusion_per_mm=args.extrusion_per_mm,
    )
    print(f"Exported {line_count} G-code lines to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
