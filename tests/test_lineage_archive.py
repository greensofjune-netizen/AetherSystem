import json
import os

import pytest

from aether_engine.lineage_archive import (
    LineageArchiveError,
    catalog_lineage,
    read_private_manifest,
    verify_lineage,
    write_private_manifest,
)


def test_catalog_fingerprints_supported_files_without_modifying_them(tmp_path):
    photo = tmp_path / "notes" / "seed.JPG"
    photo.parent.mkdir()
    photo.write_bytes(b"photo bytes")
    note = tmp_path / "grandpa.txt"
    note.write_text("original wording\n", encoding="utf-8")
    (tmp_path / "ignored.dat").write_bytes(b"not cataloged")
    photo_mtime = photo.stat().st_mtime_ns

    manifest = catalog_lineage(tmp_path, label="family archive")

    assert manifest["manifest_version"] == 1
    assert manifest["archive_label"] == "family archive"
    assert manifest["statistics"] == {
        "artifact_count": 2,
        "image_count": 1,
        "note_count": 1,
        "document_count": 0,
        "duplicate_file_count": 0,
        "skipped_symlink_count": 0,
    }
    assert [item["relative_path"] for item in manifest["artifacts"]] == [
        "grandpa.txt",
        "notes/seed.JPG",
    ]
    assert all(item["verification_status"] == "UNVERIFIED" for item in manifest["artifacts"])
    assert all(item["matrix_correlations"] == [] for item in manifest["artifacts"])
    assert photo.stat().st_mtime_ns == photo_mtime


def test_catalog_reports_duplicates_by_content_and_skips_symlinks(tmp_path):
    original = tmp_path / "original.png"
    original.write_bytes(b"same bytes")
    (tmp_path / "copy.png").write_bytes(b"same bytes")
    (tmp_path / "link.png").symlink_to(original)

    manifest = catalog_lineage(tmp_path)

    assert len(manifest["duplicate_groups"]) == 1
    assert manifest["statistics"]["duplicate_file_count"] == 1
    assert manifest["statistics"]["skipped_symlink_count"] == 1


def test_write_private_manifest_is_atomic_and_refuses_overwrite(tmp_path):
    output = tmp_path / "archive" / "manifest.json"
    manifest = catalog_lineage(tmp_path)

    written = write_private_manifest(manifest, output)

    assert json.loads(written.read_text(encoding="utf-8"))["manifest_version"] == 1
    if os.name == "posix":
        assert output.stat().st_mode & 0o077 == 0
    with pytest.raises(LineageArchiveError, match="already exists"):
        write_private_manifest(manifest, output)


def test_verify_lineage_detects_matches_changes_missing_and_new_files(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    (root / "stable.txt").write_text("stable", encoding="utf-8")
    (root / "changed.jpg").write_bytes(b"original")
    (root / "missing.png").write_bytes(b"present")
    manifest_path = tmp_path / "manifest.json"
    write_private_manifest(catalog_lineage(root), manifest_path)
    (root / "changed.jpg").write_bytes(b"altered")
    (root / "missing.png").unlink()
    (root / "new.jpeg").write_bytes(b"new")

    report = verify_lineage(root, read_private_manifest(manifest_path))

    assert report["status"] == "FAIL"
    assert report["summary"] == {
        "expected_count": 3,
        "matched_count": 1,
        "changed_count": 1,
        "missing_count": 1,
        "unexpected_count": 1,
        "skipped_symlink_count": 0,
    }
    assert report["matched"] == ["stable.txt"]
    assert report["changed"][0]["relative_path"] == "changed.jpg"
    assert report["missing"] == ["missing.png"]
    assert report["unexpected"] == ["new.jpeg"]


def test_verify_lineage_rejects_path_escape(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    manifest = {
        "manifest_version": 1,
        "artifacts": [{"relative_path": "../outside.txt", "sha256": "0" * 64}],
    }

    with pytest.raises(LineageArchiveError, match="escapes the archive"):
        verify_lineage(root, manifest)
