"""Generate a base64 PNG visualization of a spin-network boundary."""

import argparse
import base64
import io
from collections.abc import Sequence

import numpy as np


def generate_spin_network_visualization(
    num_links: int = 30,
    seed: int = 42,
) -> str:
    """Create and return a data URI for a seeded spin-network boundary plot."""
    if num_links < 1:
        raise ValueError("num_links must be at least 1")
    if seed < 0 or seed > 2**32 - 1:
        raise ValueError("seed must be between 0 and 4294967295")

    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from matplotlib.patches import Circle

    rng = np.random.RandomState(seed)
    allowed_spins = np.array([0.5, 1.0, 1.5, 2.0, 2.5, 3.0])
    spins = rng.choice(allowed_spins, size=num_links)
    radius = np.sqrt(rng.uniform(0, 0.9, size=num_links))
    theta = rng.uniform(0, 2 * np.pi, size=num_links)
    x = radius * np.cos(theta)
    y = radius * np.sin(theta)

    figure = Figure(figsize=(6, 6))
    FigureCanvasAgg(figure)
    axes = figure.subplots()
    boundary = Circle(
        (0, 0),
        1.0,
        color="#1f77b4",
        fill=False,
        linestyle="--",
        linewidth=2,
        alpha=0.5,
        label="Quantized Boundary Surface",
    )
    axes.add_patch(boundary)
    scatter = axes.scatter(
        x,
        y,
        s=spins * 150,
        c=spins,
        cmap="plasma",
        edgecolors="white",
        linewidths=1.5,
        zorder=3,
    )

    for xi, yi in zip(x, y):
        axes.plot([0, xi], [0, yi], color="gray", linestyle=":", alpha=0.3, zorder=1)

    figure.colorbar(scatter, ax=axes, label="SU(2) Spin Magnitude (j)", fraction=0.046, pad=0.04)
    axes.set_title(
        r"Loop Quantum Gravity: Spatial Boundary Puncture Arrays "
        r"($A \propto \sum \sqrt{j(j+1)}$)",
        fontsize=10,
        pad=15,
    )
    axes.set_xlim(-1.2, 1.2)
    axes.set_ylim(-1.2, 1.2)
    axes.set_axis_off()

    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", bbox_inches="tight", dpi=150)
    image = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{image}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--num-links", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    try:
        image_data_uri = generate_spin_network_visualization(
            num_links=args.num_links,
            seed=args.seed,
        )
    except ValueError as error:
        parser.error(str(error))

    print(f"base64_encoded_image:\"{image_data_uri}\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
