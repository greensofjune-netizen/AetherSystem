from __future__ import annotations

from unittest.mock import patch

import pytest

from aether_engine.jukebox import (
    TRACK_DATABASE,
    JukeboxTrackNotFoundError,
    main_loop,
    spin_vinyl,
)


def test_spin_vinyl_opens_registered_track() -> None:
    track = "polite_to_point"

    with patch("webbrowser.open") as mock_open:
        spin_vinyl(track)

    mock_open.assert_called_once_with(TRACK_DATABASE[track])


def test_spin_vinyl_raises_for_unregistered_track() -> None:
    with pytest.raises(JukeboxTrackNotFoundError) as exc_info:
        spin_vinyl("unregistered_rogue_track")

    assert "matches no entry in central registry" in str(exc_info.value)


def test_jukebox_shell_exits_on_q() -> None:
    with patch("builtins.input", return_value="q"):
        with pytest.raises(SystemExit) as exc_info:
            main_loop()

    assert exc_info.value.code == 0


@pytest.mark.parametrize(
    "menu_input, expected_track",
    [
        ("1", "polite_to_point"),
        ("2", "in_crowd"),
        ("3", "ramsey_sloopy"),
        ("4", "cold_duck_time"),
        ("5", "catch_a_thief"),
    ],
)
def test_jukebox_menu_maps_input_tokens_perfectly(
    menu_input: str, expected_track: str
) -> None:
    """Assert that selecting numeric options 1 through 5 routes to the correct structural audio token."""
    with (
        patch("builtins.input", side_effect=[menu_input, "q"]),
        patch("aether_engine.jukebox.spin_vinyl") as mock_spin,
    ):
        with pytest.raises(SystemExit):
            main_loop()

        mock_spin.assert_called_once_with(expected_track)
