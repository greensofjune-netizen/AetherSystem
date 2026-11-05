from __future__ import annotations

import sys
import webbrowser
from typing import Final, NoReturn


class JukeboxTrackNotFoundError(Exception):
    """Raised when a track token has no matching URL in the registry."""


TRACK_DATABASE: Final[dict[str, str]] = {
    "polite_to_point": "https://youtube.com",
    "in_crowd": "https://youtube.com",
    "ramsey_sloopy": "https://youtube.com",
    "cold_duck_time": "https://youtube.com",
    "catch_a_thief": "https://youtube.com",
}

_MENU_TRACKS: Final[dict[str, str]] = {
    "1": "polite_to_point",
    "2": "in_crowd",
    "3": "ramsey_sloopy",
    "4": "cold_duck_time",
    "5": "catch_a_thief",
}


def spin_vinyl(track_key: str) -> None:
    """Open the URL for a registered track token in the system browser."""
    try:
        url = TRACK_DATABASE[track_key]
    except KeyError as error:
        raise JukeboxTrackNotFoundError(
            f"Track token '{track_key}' matches no entry in central registry."
        ) from error
    webbrowser.open(url)


def display_menu() -> None:
    """Render the jukebox interactive console menu."""
    print("\n" + "=" * 50)
    print(" 🎷 AETHER SYSTEM UNIVERSAL EQUILIBRIUM JUKEBOX 🎷")
    print("=" * 50)
    print("  1. 'It's Not Polite to Point' - Gordon Goodwin")
    print("  2. 'The In Crowd' (Live) - Ramsey Lewis Trio")
    print("  3. 'Hang On Sloopy' - Ramsey Lewis")
    print("  4. 'Cold Duck Time' - McCann & Harris")
    print("  5. 'To Catch a Thief' - Gordon Goodwin")
    print("  [Q] Disengage Audio Subsystems and Return to Engine")
    print("=" * 50)


def main_loop() -> NoReturn:
    """Run the interactive jukebox until the user quits or interrupts."""
    while True:
        display_menu()
        try:
            choice = input("Select audio telemetry stream: ").strip().lower()
            if choice == "q":
                sys.exit(0)
            if choice in _MENU_TRACKS:
                spin_vinyl(_MENU_TRACKS[choice])
            else:
                print("⚠️ Invalid token signature.")
        except KeyboardInterrupt:
            sys.exit(0)
