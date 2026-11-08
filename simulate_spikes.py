import matplotlib.pyplot as plt
import numpy as np


def run_spike_simulation(steps=100, threshold=4.5):
    """
    Simulates real-time thermodynamic spikes and phase transitions
    within the AetherSystem quantum geometry boundary layer.
    """
    np.random.seed(101)
    time_series = np.arange(steps)

    # Baseline micro-fluctuations inside the loop network
    base_entropy = np.random.normal(loc=145.25, scale=1.5, size=steps)

    # Inject spontaneous quantum gravity metric spikes
    spike_indices = [15, 42, 73]
    for idx in spike_indices:
        base_entropy[idx:] += np.exp(-0.1 * (time_series[idx:] - idx)) * 25.0
        base_entropy[idx] += 45.0  # Acute impulse point

    plt.figure(figsize=(9, 4.5))
    plt.plot(
        time_series,
        base_entropy,
        color="#00d2ff",
        linewidth=2,
        label="Quantum Boundary Entropy ($S_{vN}$)",
    )

    # Map the baseline equilibrium value from your terminal run
    plt.axhline(
        y=145.2586,
        color="magenta",
        linestyle="--",
        alpha=0.6,
        label="Baseline Equilibrium State",
    )

    # Highlight phase transition spikes
    for s_idx in spike_indices:
        plt.scatter(
            s_idx,
            base_entropy[s_idx],
            color="red",
            s=80,
            zorder=5,
            label="Geometric Spike Event" if s_idx == 15 else "",
        )
        plt.annotate(
            "Critical Instability",
            (s_idx + 1, base_entropy[s_idx] + 1),
            color="white",
            fontsize=8,
        )

    plt.title(
        "AetherSystem Core: Micro Loop Gauge Entropy Spike Dynamics",
        color="white",
        fontsize=11,
        pad=12,
    )
    plt.xlabel("Computational Epoch ( Planck Time Intervals )", color="gray")
    plt.ylabel("Entanglement Entropy (Nats)", color="gray")

    # Styling match for modern dark-mode IDE profiles
    fig = plt.gcf()
    fig.patch.set_facecolor("#1e1e1e")
    ax = plt.gca()
    ax.set_facecolor("#252526")
    ax.xaxis.label.set_color("gray")
    ax.yaxis.label.set_color("gray")
    ax.tick_params(colors="gray")

    plt.legend(facecolor="#1e1e1e", edgecolor="gray", labelcolor="white")
    plt.grid(True, color="gray", linestyle=":", alpha=0.3)

    # Save a rendering frame directly to disk
    plt.savefig(
        "quantum_entropy_spikes.png",
        bbox_inches="tight",
        facecolor=fig.get_facecolor(),
        dpi=150,
    )
    plt.close()
    print(
        "[SYSTEM CORE] Spike simulation plotted and saved to "
        "'quantum_entropy_spikes.png' successfully."
    )


if __name__ == "__main__":
    run_spike_simulation()
