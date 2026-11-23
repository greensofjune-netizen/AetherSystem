#!/usr/bin/env python3
"""Build a local ISO 639-3 language registry from the official SIL table."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

ISO_639_3_URL = (
    "https://iso639-3.sil.org/sites/iso639-3/files/downloads/iso-639-3.tab"
)
DEFAULT_OUTPUT = Path("src/aether_engine/world_languages_full.json")


class RegistryBuildError(RuntimeError):
    pass


def _read_source(source: str | None) -> bytes:
    if source:
        try:
            return Path(source).expanduser().read_bytes()
        except OSError as error:
            raise RegistryBuildError(f"Could not read source file: {source}") from error
    request = urllib.request.Request(
        ISO_639_3_URL,
        headers={"User-Agent": "AetherSystem ISO-639 registry builder"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status != 200:
                raise RegistryBuildError(
                    f"ISO 639-3 download returned HTTP {response.status}."
                )
            return response.read(5_000_001)
    except urllib.error.URLError as error:
        raise RegistryBuildError(
            f"Could not download the official ISO 639-3 registry: {error}"
        ) from error


def build_registry(source_bytes: bytes) -> dict[str, Any]:
    try:
        text = source_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise RegistryBuildError("ISO 639-3 source is not valid UTF-8.") from error
    if not text.strip():
        raise RegistryBuildError("ISO 639-3 source is empty.")

    reader = csv.DictReader(text.splitlines(), delimiter="\t")
    required = {
        "Id",
        "Part1",
        "Part2b",
        "Part2t",
        "Scope",
        "Language_Type",
        "Ref_Name",
    }
    if reader.fieldnames is None or not required.issubset(reader.fieldnames):
        raise RegistryBuildError("ISO 639-3 source columns are not recognized.")

    languages: list[dict[str, Any]] = []
    identifiers: set[str] = set()
    names: set[tuple[str, str]] = set()
    for row_number, row in enumerate(reader, start=2):
        code = (row.get("Id") or "").strip().lower()
        name = (row.get("Ref_Name") or "").strip()
        if len(code) != 3 or not code.isalpha() or not name:
            raise RegistryBuildError(
                f"Invalid ISO 639-3 record at source line {row_number}."
            )
        if code in identifiers:
            raise RegistryBuildError(f"Duplicate ISO 639-3 identifier: {code}.")
        identifiers.add(code)
        name_key = (name.casefold(), code)
        if name_key in names:
            raise RegistryBuildError(f"Duplicate language name/code pair: {name}.")
        names.add(name_key)
        languages.append(
            {
                "iso_639_3": code,
                "iso_639_2_b": (row.get("Part2b") or "").strip().lower() or None,
                "iso_639_2_t": (row.get("Part2t") or "").strip().lower() or None,
                "iso_639_1": (row.get("Part1") or "").strip().lower() or None,
                "scope": (row.get("Scope") or "").strip() or None,
                "type": (row.get("Language_Type") or "").strip() or None,
                "name": name,
                "comment": (row.get("Comment") or "").strip() or None,
            }
        )

    languages.sort(key=lambda entry: entry["iso_639_3"])
    if not 7_000 <= len(languages) <= 10_000:
        raise RegistryBuildError(
            f"Unexpected ISO 639-3 record count: {len(languages)}."
        )
    return {
        "schema_version": 1,
        "source": ISO_639_3_URL,
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "language_count": len(languages),
        "languages": languages,
    }


def write_registry(registry: dict[str, Any], output: str | Path) -> Path:
    destination = Path(output).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        registry, indent=2, ensure_ascii=False, sort_keys=True
    ) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise RegistryBuildError(
            f"Could not write registry atomically: {destination}"
        ) from error
    return destination


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the local ISO 639-3 registry used by Copernicus."
    )
    parser.add_argument(
        "--source",
        help="existing iso-639-3.tab file; omitted downloads the official table",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help=f"registry JSON path (default: {DEFAULT_OUTPUT})",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        source = _read_source(args.source)
        output = write_registry(build_registry(source), args.output)
    except RegistryBuildError as error:
        print(f"build_world_languages_json: {error}", file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
