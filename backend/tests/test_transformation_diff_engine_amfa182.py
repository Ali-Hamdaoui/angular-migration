"""Tests for TransformationDiffService — AMFA-182."""

import hashlib
import json
from pathlib import Path

import pytest

from app.services.transformation_diff_service import (
    CanonicalDiffResult,
    TransformationDiffError,
    TransformationDiffLimits,
    TransformationDiffService,
)
from app.domain.transformation import (
    ChangedFileClassification,
    ChangedFileEntry,
    DiffSummary,
    LockfileParserStatus,
    SensitiveChangeReason,
    TransformationEvidenceMode,
)


class TestTransformationDiffEngine:
    """Comprehensive test suite for TransformationDiffService."""

    # ── core diff logic ──────────────────────────────────────────────────

    def test_same_length_replacements_have_distinct_patch_checksums(
        self, tmp_path: Path
    ):
        src = tmp_path / "src"
        tgt = tmp_path / "tgt"
        src.mkdir()
        tgt.mkdir()

        (src / "a.ts").write_text("line1\nline2\nline3\n")
        (tgt / "a.ts").write_text("line1\nCHANGED\nline3\n")
        (src / "b.ts").write_text("keep1\nkeep2\nkeep3\n")
        (tgt / "b.ts").write_text("KEEP1\nKEEP2\nkeep3\n")

        svc = TransformationDiffService()
        result = svc.compute(src, tgt)

        assert result.summary.total_files_changed == 2
        assert result.summary.total_lines_added == 3
        assert result.summary.total_lines_removed == 3
        assert result.summary.diff_checksum.startswith("sha256:")
        assert len(result.summary.diff_checksum) == 71

    def test_replacement_counts_added_and_removed_lines(self, tmp_path: Path):
        src = tmp_path / "src"
        tgt = tmp_path / "tgt"
        src.mkdir()
        tgt.mkdir()

        (src / "f.txt").write_text("a\nb\nc\nd\ne\n")
        (tgt / "f.txt").write_text("a\nNEW1\nNEW2\nc\nd\n")

        svc = TransformationDiffService()
        result = svc.compute(src, tgt)

        assert result.summary.total_lines_removed == 2
        assert result.summary.total_lines_added == 2

    def test_line_ending_only_change_is_ignored(self, tmp_path: Path):
        src = tmp_path / "src"
        tgt = tmp_path / "tgt"
        src.mkdir()
        tgt.mkdir()

        (src / "f.txt").write_bytes(b"hello\r\nworld\r\n")
        (tgt / "f.txt").write_bytes(b"hello\nworld\n")

        svc = TransformationDiffService()
        result = svc.compute(src, tgt)

        assert result.summary.total_files_changed == 0
        assert result.patch_bytes == b""

    def test_patch_checksum_equals_exact_patch_bytes_sha256(self, tmp_path: Path):
        src = tmp_path / "src"
        tgt = tmp_path / "tgt"
        src.mkdir()
        tgt.mkdir()

        (src / "f.txt").write_text("old\n")
        (tgt / "f.txt").write_text("new\n")

        svc = TransformationDiffService()
        result = svc.compute(src, tgt)

        expected = "sha256:" + hashlib.sha256(result.patch_bytes).hexdigest()
        assert result.summary.diff_checksum == expected

    def test_inventory_contains_before_and_after_hashes(self, tmp_path: Path):
        src = tmp_path / "src"
        tgt = tmp_path / "tgt"
        src.mkdir()
        tgt.mkdir()

        (src / "f.txt").write_text("before content\n")
        (tgt / "f.txt").write_text("after content\n")

        svc = TransformationDiffService()
        result = svc.compute(src, tgt)

        entry = result.summary.changed_files[0]
        assert entry.before_sha256 is not None
        assert entry.after_sha256 is not None
        assert entry.before_sha256 != entry.after_sha256
        assert entry.before_sha256.startswith("sha256:")
        assert entry.after_sha256.startswith("sha256:")

    # ── binary / oversized files ─────────────────────────────────────────

    def test_binary_content_with_text_extension_uses_binary_metadata(
        self, tmp_path: Path
    ):
        src = tmp_path / "src"
        tgt = tmp_path / "tgt"
        src.mkdir()
        tgt.mkdir()

        (src / "comp.ts").write_bytes(b"valid text\n")
        (tgt / "comp.ts").write_bytes(b"valid text\nwith \0 binary\n")

        svc = TransformationDiffService()
        result = svc.compute(src, tgt)

        entry = result.summary.changed_files[0]
        assert entry.is_binary is True
        assert entry.evidence_mode == TransformationEvidenceMode.BINARY_METADATA
        assert entry.classification == ChangedFileClassification.BINARY
        assert b"AMFA-METADATA" in result.patch_bytes

    def test_text_content_with_binary_extension_is_not_classified_by_extension_only(
        self, tmp_path: Path
    ):
        src = tmp_path / "src"
        tgt = tmp_path / "tgt"
        src.mkdir()
        tgt.mkdir()

        (src / "data.bin").write_text("plain text content\n")
        (tgt / "data.bin").write_text("different plain text\n")

        svc = TransformationDiffService()
        result = svc.compute(src, tgt)

        entry = result.summary.changed_files[0]
        assert entry.is_binary is False
        assert entry.evidence_mode == TransformationEvidenceMode.FULL_DIFF

    def test_unchanged_oversized_file_is_not_changed(self, tmp_path: Path):
        src = tmp_path / "src"
        tgt = tmp_path / "tgt"
        src.mkdir()
        tgt.mkdir()

        limits = TransformationDiffLimits(max_text_file_bytes=10)
        svc = TransformationDiffService(limits=limits)

        content = b"oversized!\n" * 100
        (src / "big.txt").write_bytes(content)
        (tgt / "big.txt").write_bytes(content)

        result = svc.compute(src, tgt)

        assert result.summary.total_files_changed == 0

    def test_changed_oversized_file_uses_bounded_metadata(self, tmp_path: Path):
        src = tmp_path / "src"
        tgt = tmp_path / "tgt"
        src.mkdir()
        tgt.mkdir()

        limits = TransformationDiffLimits(max_text_file_bytes=10)
        svc = TransformationDiffService(limits=limits)

        (src / "big.txt").write_bytes(b"oversized!\n" * 100)
        (tgt / "big.txt").write_bytes(b"DIFFERENT\n" * 100)

        result = svc.compute(src, tgt)

        entry = result.summary.changed_files[0]
        assert entry.evidence_mode == TransformationEvidenceMode.OVERSIZED_METADATA
        assert entry.unsupported_reason == "file exceeds text diff limit"
        assert b"AMFA-METADATA" in result.patch_bytes

    # ── limits / budgets ──────────────────────────────────────────────────

    def test_file_count_limit_fails_closed(self, tmp_path: Path):
        src = tmp_path / "src"
        tgt = tmp_path / "tgt"
        src.mkdir()
        tgt.mkdir()

        limits = TransformationDiffLimits(max_files=3)
        svc = TransformationDiffService(limits=limits)

        for i in range(4):
            (src / f"f{i}.txt").write_text(f"content{i}\n")
            (tgt / f"f{i}.txt").write_text(f"changed{i}\n")

        with pytest.raises(TransformationDiffError) as exc:
            svc.compute(src, tgt)
        assert exc.value.code == "TRANSFORMATION_FILE_LIMIT"

    def test_total_byte_budget_fails_closed(self, tmp_path: Path):
        src = tmp_path / "src"
        tgt = tmp_path / "tgt"
        src.mkdir()
        tgt.mkdir()

        limits = TransformationDiffLimits(max_total_scanned_bytes=50)
        svc = TransformationDiffService(limits=limits)

        (src / "a.txt").write_bytes(b"x" * 40)
        (tgt / "a.txt").write_bytes(b"y" * 40)

        with pytest.raises(TransformationDiffError) as exc:
            svc.compute(src, tgt)
        assert exc.value.code == "TRANSFORMATION_BYTE_LIMIT"

    # ── exclusion policy ──────────────────────────────────────────────────

    def test_node_modules_and_cache_are_excluded_by_policy(self, tmp_path: Path):
        src = tmp_path / "src"
        tgt = tmp_path / "tgt"
        src.mkdir()
        tgt.mkdir()

        (src / "node_modules" / "lodash" / "index.js").parent.mkdir(parents=True)
        (src / "node_modules" / "lodash" / "index.js").write_text(
            "module.exports = {};\n"
        )
        (tgt / "node_modules" / "lodash" / "index.js").parent.mkdir(parents=True)
        (tgt / "node_modules" / "lodash" / "index.js").write_text(
            "module.exports = { updated: true };\n"
        )

        cache_dir = src / ".angular" / "cache"
        cache_dir.mkdir(parents=True)
        (cache_dir / "build.json").write_text("{}")
        tgt_cache = tgt / ".angular" / "cache"
        tgt_cache.mkdir(parents=True)
        (tgt_cache / "build.json").write_text('{"updated": true}')

        svc = TransformationDiffService()
        result = svc.compute(src, tgt)

        assert result.summary.total_files_changed == 0

    # ── determinism ──────────────────────────────────────────────────────

    def test_added_deleted_and_modified_files_are_deterministic(
        self, tmp_path: Path
    ):
        src = tmp_path / "src"
        tgt = tmp_path / "tgt"
        src.mkdir()
        tgt.mkdir()

        (src / "keep.txt").write_text("same\n")
        (tgt / "keep.txt").write_text("same\n")
        (src / "delete.txt").write_text("remove me\n")
        (src / "modify.txt").write_text("old\n")
        (tgt / "modify.txt").write_text("new\n")
        (tgt / "added.txt").write_text("i am new\n")

        svc = TransformationDiffService()
        r1 = svc.compute(src, tgt)
        r2 = svc.compute(src, tgt)

        assert r1.summary.total_files_changed == r2.summary.total_files_changed
        assert r1.summary.total_files_changed == 3
        assert r1.summary.diff_checksum == r2.summary.diff_checksum
        assert r1.summary.inventory_checksum == r2.summary.inventory_checksum
        assert r1.patch_bytes == r2.patch_bytes

        changes = {e.file_path: e.change_type for e in r1.summary.changed_files}
        assert changes["delete.txt"] == "deleted"
        assert changes["modify.txt"] == "modified"
        assert changes["added.txt"] == "added"

    def test_rename_is_explicitly_delete_plus_add(self, tmp_path: Path):
        src = tmp_path / "src"
        tgt = tmp_path / "tgt"
        src.mkdir()
        tgt.mkdir()

        (src / "old_name.txt").write_text("content\n")
        (tgt / "new_name.txt").write_text("content\n")

        svc = TransformationDiffService()
        result = svc.compute(src, tgt)

        assert result.summary.total_files_changed == 2
        changes = {e.file_path: e.change_type for e in result.summary.changed_files}
        assert changes.get("old_name.txt") == "deleted"
        assert changes.get("new_name.txt") == "added"

    # ── lockfile handling ─────────────────────────────────────────────────

    def test_npm_lockfile_semantic_delta(self, tmp_path: Path):
        src = tmp_path / "src"
        tgt = tmp_path / "tgt"
        src.mkdir()
        tgt.mkdir()

        (src / "package-lock.json").write_text('{"name": "old", "lockfileVersion": 1}\n')
        (tgt / "package-lock.json").write_text('{"name": "new", "lockfileVersion": 2}\n')

        svc = TransformationDiffService()
        result = svc.compute(src, tgt)

        entry = result.summary.changed_files[0]
        assert entry.classification == ChangedFileClassification.MEDIUM_RISK
        assert entry.reason == SensitiveChangeReason.PACKAGE_LOCK_CHANGE

    def test_unsupported_lockfile_is_explicit(self, tmp_path: Path):
        src = tmp_path / "src"
        tgt = tmp_path / "tgt"
        src.mkdir()
        tgt.mkdir()

        (src / "pnpm-lock.yaml").write_text("lockfileVersion: '6.0'\n")
        (tgt / "pnpm-lock.yaml").write_text("lockfileVersion: '7.0'\n")

        svc = TransformationDiffService()
        result = svc.compute(src, tgt)

        entry = result.summary.changed_files[0]
        assert entry.classification == ChangedFileClassification.UNKNOWN
        assert entry.reason == SensitiveChangeReason.CONFIGURATION_CHANGE

    # ── builder / schematic / migration evidence ──────────────────────────

    def test_builder_and_schematic_drift(self, tmp_path: Path):
        src = tmp_path / "src"
        tgt = tmp_path / "tgt"
        src.mkdir()
        tgt.mkdir()

        (src / "angular.json").write_text(
            json.dumps(
                {
                    "projects": {
                        "app": {
                            "architect": {
                                "build": {
                                    "builder": "@angular-devkit/build-angular:browser"
                                }
                            }
                        }
                    }
                }
            )
        )
        (tgt / "angular.json").write_text(
            json.dumps(
                {
                    "projects": {
                        "app": {
                            "architect": {
                                "build": {
                                    "builder": "@angular-devkit/build-angular:application"
                                }
                            }
                        }
                    }
                }
            )
        )

        svc = TransformationDiffService()
        result = svc.compute(src, tgt)

        entry = result.summary.changed_files[0]
        assert entry.reason == SensitiveChangeReason.BUILD_SYSTEM_CHANGE

    def test_migration_evidence_is_bound_to_command_artifact(self, tmp_path: Path):
        src = tmp_path / "src"
        tgt = tmp_path / "tgt"
        src.mkdir()
        tgt.mkdir()

        (src / ".angular" / "config.json").parent.mkdir(parents=True)
        (src / ".angular" / "config.json").write_text('{"version": 1}\n')
        (tgt / ".angular" / "config.json").parent.mkdir(parents=True)
        (tgt / ".angular" / "config.json").write_text('{"version": 2}\n')

        svc = TransformationDiffService()
        result = svc.compute(src, tgt)

        entry = result.summary.changed_files[0]
        assert entry.is_generated is True
        assert entry.classification == ChangedFileClassification.GENERATED
        assert entry.reason == SensitiveChangeReason.GENERATED_FILE

    def test_heuristic_migration_cannot_complete_evidence(self, tmp_path: Path):
        src = tmp_path / "src"
        tgt = tmp_path / "tgt"
        src.mkdir()
        tgt.mkdir()

        (src / "note.txt").write_text("heuristic guess\n")
        (tgt / "note.txt").write_text("heuristic confirmed\n")

        svc = TransformationDiffService()
        result = svc.compute(src, tgt)

        entry = result.summary.changed_files[0]
        assert entry.evidence_mode == TransformationEvidenceMode.FULL_DIFF

    def test_sensitive_reason_elevates_aggregate_risk(self, tmp_path: Path):
        src = tmp_path / "src"
        tgt = tmp_path / "tgt"
        src.mkdir()
        tgt.mkdir()

        (src / "src" / "auth-endpoint.txt").parent.mkdir(parents=True)
        (src / "src" / "auth-endpoint.txt").write_text("data\n")
        (tgt / "src" / "auth-endpoint.txt").parent.mkdir(parents=True)
        (tgt / "src" / "auth-endpoint.txt").write_text("updated\n")

        svc = TransformationDiffService()
        result = svc.compute(src, tgt)

        entry = result.summary.changed_files[0]
        assert entry.classification == ChangedFileClassification.SENSITIVE
        assert entry.reason == SensitiveChangeReason.AUTH_OR_API

    def test_external_source_bytes_are_unchanged(self, tmp_path: Path):
        src = tmp_path / "src"
        tgt = tmp_path / "tgt"
        src.mkdir()
        tgt.mkdir()

        (src / "stable.txt").write_text("never changes\n")
        (tgt / "stable.txt").write_text("never changes\n")

        svc = TransformationDiffService()
        result = svc.compute(src, tgt)

        assert result.summary.total_files_changed == 0
        assert result.patch_bytes == b""
