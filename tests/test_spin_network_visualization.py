import base64

import pytest

from aether_engine.spin_network_visualization import (
    generate_spin_network_visualization,
    main,
)


def test_visualization_returns_deterministic_png_data_uri():
    first = generate_spin_network_visualization(num_links=4, seed=7)
    second = generate_spin_network_visualization(num_links=4, seed=7)

    assert first == second
    prefix, encoded_image = first.split(",", maxsplit=1)
    assert prefix == "data:image/png;base64"
    assert base64.b64decode(encoded_image, validate=True).startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.parametrize(
    ("num_links", "seed"),
    [(0, 42), (-1, 42), (1, -1), (1, 2**32)],
)
def test_visualization_rejects_invalid_parameters(num_links, seed):
    with pytest.raises(ValueError):
        generate_spin_network_visualization(num_links, seed)


def test_visualization_cli_prints_encoded_image(capsys):
    assert main(["--num-links", "1", "--seed", "7"]) == 0
    assert capsys.readouterr().out.startswith('base64_encoded_image:"data:image/png;base64,')
