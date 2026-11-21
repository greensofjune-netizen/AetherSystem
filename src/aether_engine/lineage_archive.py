from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MANIFEST_VERSION = 1
_IMAGE_SUFFIXES = {".avif", ".heic", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
_NOTE_SUFFIXES = {".md", ".rtf", ".txt"}
_DOCUMENT_SUFFIXES = {".doc", ".docx", ".pdf"}
_SUPPORTED_SUFFIXES = _IMAGE_SUFFIXES | _NOTE_SUFFIXES | _DOCUMENT_SUFFIXES


class LineageArchiveError(RuntimeError):
    pass


def _utc_from_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _kind_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in _IMAGE_SUFFIXES:
        return "image"
    if suffix in _NOTE_SUFFIXES:
        return "note"
    if suffix in _DOCUMENT_SUFFIXES:
        return "document"
    raise LineageArchiveError(f"Unsupported file type: {path.name}")


def catalog_lineage(
    source: str | Path,
    *,
    label: str = "private-family-lineage",
) -> dict[str, Any]:
    root = Path(source).expanduser().resolve()
    if not root.is_dir():
        raise LineageArchiveError(f"Source directory does not exist: {root}")
    if not label.strip():
        raise ValueError("label must be a non-empty string")

    artifacts: list[dict[str, Any]] = []
    skipped_symlinks = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            skipped_symlinks += 1
            continue
        if not path.is_file() or path.suffix.lower() not in _SUPPORTED_SUFFIXES:
            continue
        stat = path.stat()
        digest = _sha256(path)
        relative_path = path.relative_to(root).as_posix()
        artifacts.append(
            {
                "artifact_id": f"artifact-{digest[:16]}",
                "relative_path": relative_path,
                "sha256": digest,
                "size_bytes": stat.st_size,
                "kind": _kind_for(path),
                "modified_at_utc": _utc_from_timestamp(stat.st_mtime),
                "verification_status": "UNVERIFIED",
                "provenance": {
                    "source_role": "PENDING_CLASSIFICATION",
                    "attribution": "UNVERIFIED",
                },
                "matrix_correlations": [],
            }
        )

    duplicate_groups: list[dict[str, Any]] = []
    by_digest: dict[str, list[str]] = {}
    for artifact in artifacts:
        by_digest.setdefault(artifact["sha256"], []).append(artifact["artifact_id"])
    for digest, artifact_ids in sorted(by_digest.items()):
        if len(artifact_ids) > 1:
            duplicate_groups.append(
                {
                    "sha256": digest,
                    "artifact_ids": artifact_ids,
                }
            )

    return {
        "manifest_version": MANIFEST_VERSION,
        "archive_label": label.strip(),
        "created_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "evidence_policy": {
            "originals": "NEVER_MODIFIED_BY_CATALOGER",
            "default_status": "UNVERIFIED",
            "correlations": "REQUIRE_EXPLICIT_EVIDENCE_STATUS",
            "publication": "PRIVATE_UNLESS_REVIEWED",
        },
        "artifacts": artifacts,
        "duplicate_groups": duplicate_groups,
        "statistics": {
            "artifact_count": len(artifacts),
            "image_count": sum(item["kind"] == "image" for item in artifacts),
            "note_count": sum(item["kind"] == "note" for item in artifacts),
            "document_count": sum(item["kind"] == "document" for item in artifacts),
            "duplicate_file_count": sum(
                len(group["artifact_ids"]) - 1 for group in duplicate_groups
            ),
            "skipped_symlink_count": skipped_symlinks,
        },
    }


def write_private_manifest(
    manifest: dict[str, Any],
    output: str | Path,
    *,
    force: bool = False,
) -> Path:
    destination = Path(output).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.is_symlink():
            raise LineageArchiveError("Manifest output cannot be a symbolic link.")
        if not force:
            raise LineageArchiveError(f"Manifest already exists: {destination}")
    payload = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        destination.chmod(0o600)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise LineageArchiveError(
            f"Could not write manifest atomically: {destination}"
        ) from error
    return destination


def _safe_manifest_path(root: Path, relative_path: object) -> Path:
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise LineageArchiveError("Manifest artifact path must be a non-empty string.")
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise LineageArchiveError(
            f"Manifest artifact path escapes the archive: {relative_path}"
        )
    candidate = root / relative
    try:
        candidate.resolve(strict=False).relative_to(root)
    except ValueError as error:
        raise LineageArchiveError(
            f"Manifest artifact path escapes the archive: {relative_path}"
        ) from error
    return candidate


def read_private_manifest(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    if source.is_symlink():
        raise LineageArchiveError("Manifest cannot be a symbolic link.")
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise LineageArchiveError(f"Manifest could not be read: {source}") from error
    if not isinstance(value, dict):
        raise LineageArchiveError("Manifest root must be a JSON object.")
    if value.get("manifest_version") != MANIFEST_VERSION:
        raise LineageArchiveError("Manifest version is not supported.")
    if not isinstance(value.get("artifacts"), list):
        raise LineageArchiveError("Manifest artifacts must be a list.")
    return value


def verify_lineage(
    source: str | Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    root = Path(source).expanduser().resolve()
    if not root.is_dir():
        raise LineageArchiveError(f"Source directory does not exist: {root}")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise LineageArchiveError("Manifest artifacts must be a list.")

    expected: dict[str, dict[str, Any]] = {}
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise LineageArchiveError("Manifest artifact entries must be objects.")
        relative_path = artifact.get("relative_path")
        digest = artifact.get("sha256")
        if not isinstance(relative_path, str) or not isinstance(digest, str):
            raise LineageArchiveError(
                "Manifest artifact requires relative_path and sha256 strings."
            )
        _safe_manifest_path(root, relative_path)
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise LineageArchiveError(
                f"Manifest SHA-256 is invalid for {relative_path}."
            )
        if relative_path in expected:
            raise LineageArchiveError(
                f"Manifest contains duplicate artifact path: {relative_path}"
            )
        expected[relative_path] = artifact

    current: dict[str, Path] = {}
    skipped_symlinks = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            skipped_symlinks += 1
            continue
        if path.is_file() and path.suffix.lower() in _SUPPORTED_SUFFIXES:
            current[path.relative_to(root).as_posix()] = path

    matched: list[str] = []
    changed: list[dict[str, str]] = []
    missing: list[str] = []
    for relative_path, artifact in sorted(expected.items()):
        path = _safe_manifest_path(root, relative_path)
        if path.is_symlink():
            missing.append(relative_path)
            continue
        if relative_path not in current:
            missing.append(relative_path)
            continue
        actual_digest = _sha256(path)
        if actual_digest == artifact["sha256"]:
            matched.append(relative_path)
        else:
            changed.append(
                {
                    "relative_path": relative_path,
                    "expected_sha256": artifact["sha256"],
                    "actual_sha256": actual_digest,
                }
            )

    unexpected = sorted(set(current) - set(expected))
    passed = not changed and not missing and not unexpected
    return {
        "report_version": 1,
        "verified_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "status": "PASS" if passed else "FAIL",
        "baseline": "PRIVATE_SHA256_MANIFEST",
        "comparison": "MANUAL_OR_CURRENT_WORKFLOW",
        "integrity_claim": (
            "All supported files matched the recorded SHA-256 manifest; "
            "this detects byte changes and missing or new supported files."
            if passed
            else "Archive differs from the recorded SHA-256 manifest."
        ),
        "limitations": [
            "Hashes do not authenticate authorship or prove scientific truth.",
            "Verification is limited to supported regular files and bytes present now.",
            "Symlinks are skipped and unsupported file types are not verified.",
        ],
        "summary": {
            "expected_count": len(expected),
            "matched_count": len(matched),
            "changed_count": len(changed),
            "missing_count": len(missing),
            "unexpected_count": len(unexpected),
            "skipped_symlink_count": skipped_symlinks,
        },
        "matched": matched,
        "changed": changed,
        "missing": missing,
        "unexpected": unexpected,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aether-lineage-archive",
        description=(
            "Privately catalog family photographs and notes without changing originals."
        ),
    )
    parser.add_argument("source", help="directory containing photographs and notes")
    parser.add_argument(
        "--output",
        default=".aether-lineage/manifest.json",
        help="private manifest path (default: .aether-lineage/manifest.json)",
    )
    parser.add_argument(
        "--label",
        default="private-family-lineage",
        help="short label stored in the manifest",
    )
    parser.add_argument("--force", action="store_true", help="replace an existing manifest")
    parser.add_argument(
        "--verify-manifest",
        help="verify source against an existing private manifest instead of cataloging",
    )
    parser.add_argument(
        "--verification-report",
        help="optionally write verification results to a private JSON file",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.verify_manifest:
            report = verify_lineage(args.source, read_private_manifest(args.verify_manifest))
            if args.verification_report:
                write_private_manifest(
                    report,
                    args.verification_report,
                    force=args.force,
                )
            print(json.dumps(report, sort_keys=True))
            return 0 if report["status"] == "PASS" else 2
        manifest = catalog_lineage(args.source, label=args.label)
        output = write_private_manifest(manifest, args.output, force=args.force)
    except (LineageArchiveError, ValueError, OSError) as error:
        print(f"aether-lineage-archive: {error}", file=sys.stderr)
        return 1
    statistics = manifest["statistics"]
    print(
        json.dumps(
            {
                "manifest": str(output),
                "artifacts": statistics["artifact_count"],
                "duplicates": statistics["duplicate_file_count"],
                "skipped_symlinks": statistics["skipped_symlink_count"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
