"""Canonical workspace fingerprint profile contract (T01).

Pins the single authoritative workspace fingerprint implementation and proves
every planning and Transformer consumer resolves to it: no scope may retain an
independent fingerprint algorithm.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.patch_apply_service import _fingerprint_manifest
from app.services.stage_preparation_primitives import StageSandboxCopier
from app.services.validation_runner import ValidationRunner
from app.services.workspace_fingerprint import (
    PLANNING_FINGERPRINT_PROFILE,
    SOURCE_CONFIG_FINGERPRINT_PROFILE,
    STAGE_FINGERPRINT_PROFILE,
    WORKSPACE_FINGERPRINT_VERSION,
    WorkspaceFingerprintProfile,
    encode_fingerprint,
    workspace_fingerprint_v1,
)
from app.services.workspace_integrity_service import WorkspaceIntegrityService
from app.workspaces.baseline import baseline_tree_fingerprint

DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def _write_tree(root: Path, files: dict[str, str]) -> Path:
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def _empty_tree(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    return root


class TestVersionedProfileIdentity:
    def test_profile_version_is_stable_and_documented(self):
        assert WORKSPACE_FINGERPRINT_VERSION == "workspace-fingerprint-v1"
        for profile in (PLANNING_FINGERPRINT_PROFILE, STAGE_FINGERPRINT_PROFILE, SOURCE_CONFIG_FINGERPRINT_PROFILE):
            assert profile.version == WORKSPACE_FINGERPRINT_VERSION

    def test_scopes_are_named_profiles(self):
        assert PLANNING_FINGERPRINT_PROFILE.excluded_names == frozenset({"node_modules", ".angular", "dist", "coverage"})
        assert STAGE_FINGERPRINT_PROFILE.excluded_names == frozenset()
        assert "dist" in SOURCE_CONFIG_FINGERPRINT_PROFILE.excluded_names

    def test_fingerprint_format(self, tmp_path):
        root = _write_tree(tmp_path / "workspace", {"package.json": "{}"})
        assert DIGEST_PATTERN.match(workspace_fingerprint_v1(root))

    def test_custom_profile_excludes_named_roots(self, tmp_path):
        root = _write_tree(tmp_path / "workspace", {"src/main.ts": "x", "node_modules/a.js": "y"})
        profile = WorkspaceFingerprintProfile(excluded_names=frozenset({"node_modules"}))
        assert profile.fingerprint(root) == workspace_fingerprint_v1(root, exclude=frozenset({"node_modules"}))


class TestDeterminismAndSensitivity:
    def test_deterministic_across_runs(self, tmp_path):
        root = _write_tree(tmp_path / "workspace", {"a.txt": "alpha", "b/c.txt": "beta"})
        assert workspace_fingerprint_v1(root) == workspace_fingerprint_v1(root)

    def test_equal_trees_produce_same_digest(self, tmp_path):
        first = _write_tree(tmp_path / "one", {"src/main.ts": "x", "package.json": "{}"})
        second = _write_tree(tmp_path / "two", {"src/main.ts": "x", "package.json": "{}"})
        assert workspace_fingerprint_v1(first) == workspace_fingerprint_v1(second)

    def test_changed_content_changes_digest(self, tmp_path):
        root = _write_tree(tmp_path / "workspace", {"a.txt": "before"})
        before = workspace_fingerprint_v1(root)
        (root / "a.txt").write_text("after", encoding="utf-8")
        assert workspace_fingerprint_v1(root) != before

    def test_changed_path_changes_digest(self, tmp_path):
        root = _write_tree(tmp_path / "workspace", {"a.txt": "same"})
        before = workspace_fingerprint_v1(root)
        (root / "a.txt").rename(root / "b.txt")
        assert workspace_fingerprint_v1(root) != before

    def test_swapped_content_is_detected(self, tmp_path):
        root = _write_tree(tmp_path / "workspace", {"a.txt": "one", "b.txt": "two"})
        before = workspace_fingerprint_v1(root)
        (root / "a.txt").write_text("two", encoding="utf-8")
        (root / "b.txt").write_text("one", encoding="utf-8")
        assert workspace_fingerprint_v1(root) != before

    def test_stream_encoding_is_length_prefix_bound(self):
        first = encode_fingerprint([("ab", b"c"), ("a", b"bc")])
        second = encode_fingerprint([("a", b"bc"), ("ab", b"c")])
        assert first == second
        boundary = encode_fingerprint([("a", b"b")])
        assert boundary != encode_fingerprint([("ab", b"")])


class TestExclusionPolicy:
    def test_planning_profile_excludes_volatile_roots(self, tmp_path):
        root = _write_tree(tmp_path / "workspace", {"src/main.ts": "x", "package.json": "{}"})
        before = PLANNING_FINGERPRINT_PROFILE.fingerprint(root)
        for volatile in ("node_modules", ".angular", "dist", "coverage"):
            _write_tree(root, {f"{volatile}/generated.bin": "generated"})
        assert PLANNING_FINGERPRINT_PROFILE.fingerprint(root) == before

    def test_planning_profile_excludes_nested_volatile_roots(self, tmp_path):
        root = _write_tree(tmp_path / "workspace", {"src/main.ts": "x"})
        before = PLANNING_FINGERPRINT_PROFILE.fingerprint(root)
        _write_tree(root, {"src/node_modules/dep.js": "nested"})
        assert PLANNING_FINGERPRINT_PROFILE.fingerprint(root) == before

    def test_stage_profile_hashes_every_file(self, tmp_path):
        root = _write_tree(tmp_path / "workspace", {"src/main.ts": "x"})
        before = STAGE_FINGERPRINT_PROFILE.fingerprint(root)
        _write_tree(root, {"dist/bundle.js": "generated"})
        assert STAGE_FINGERPRINT_PROFILE.fingerprint(root) != before

    def test_source_config_profile_excludes_generated_outputs(self, tmp_path):
        root = _write_tree(tmp_path / "workspace", {"src/main.ts": "x", "package.json": "{}"})
        before = SOURCE_CONFIG_FINGERPRINT_PROFILE.fingerprint(root)
        _write_tree(root, {"dist/bundle.js": "generated", "node_modules/dep.js": "dep"})
        assert SOURCE_CONFIG_FINGERPRINT_PROFILE.fingerprint(root) == before

    def test_scopes_converge_on_clean_trees(self, tmp_path):
        root = _write_tree(tmp_path / "workspace", {"src/main.ts": "x", "package.json": "{}"})
        assert PLANNING_FINGERPRINT_PROFILE.fingerprint(root) == STAGE_FINGERPRINT_PROFILE.fingerprint(root) == workspace_fingerprint_v1(root)

    def test_planning_exclusion_matches_pruned_stage_tree(self, tmp_path):
        root = _write_tree(tmp_path / "workspace", {"src/main.ts": "x", "package.json": "{}"})
        _write_tree(root, {"node_modules/dep.js": "dep", "dist/bundle.js": "bundle"})
        pruned = _write_tree(tmp_path / "pruned", {"src/main.ts": "x", "package.json": "{}"})
        assert PLANNING_FINGERPRINT_PROFILE.fingerprint(root) == STAGE_FINGERPRINT_PROFILE.fingerprint(pruned)


class TestConsumerConvergence:
    def test_workspace_integrity_resolves_to_planning_profile(self, tmp_path, monkeypatch):
        root = _write_tree(tmp_path / "workspace", {"angular.json": "{}"})
        expected = PLANNING_FINGERPRINT_PROFILE.fingerprint(root)
        assert WorkspaceIntegrityService.fingerprint(root) == expected

        def spy(root, *, exclude=frozenset()):
            return "spy:" + workspace_fingerprint_v1(root, exclude=exclude)

        monkeypatch.setattr("app.services.workspace_fingerprint.workspace_fingerprint_v1", spy)
        assert WorkspaceIntegrityService.fingerprint(root) == "spy:" + expected

    def test_baseline_tree_fingerprint_resolves_to_planning_profile(self, tmp_path):
        root = _write_tree(tmp_path / "workspace", {"angular.json": "{}", "node_modules/x.js": "x"})
        assert baseline_tree_fingerprint(root) == PLANNING_FINGERPRINT_PROFILE.fingerprint(root)

    def test_stage_copier_resolves_to_stage_profile(self, tmp_path, monkeypatch):
        root = _write_tree(tmp_path / "workspace", {"src/main.ts": "x", "dist/bundle.js": "b"})
        expected = STAGE_FINGERPRINT_PROFILE.fingerprint(root)
        assert StageSandboxCopier.fingerprint(root) == expected

        def spy(root, *, exclude=frozenset()):
            return "spy:" + workspace_fingerprint_v1(root, exclude=exclude)

        monkeypatch.setattr("app.services.workspace_fingerprint.workspace_fingerprint_v1", spy)
        assert StageSandboxCopier.fingerprint(root) == "spy:" + expected

    def test_stage_copy_report_fingerprint_is_canonical(self, tmp_path):
        source = _write_tree(tmp_path / "source", {"src/main.ts": "x"})
        target = tmp_path / "stage"
        report = StageSandboxCopier().copy(source, target)
        assert report.fingerprint == STAGE_FINGERPRINT_PROFILE.fingerprint(target)

    def test_patch_apply_manifest_fingerprint_resolves_to_canonical_stream(self, tmp_path):
        root = _write_tree(tmp_path / "workspace", {"src/main.ts": "x", "package.json": "{}"})
        assert _fingerprint_manifest({"src/main.ts": b"x", "package.json": b"{}"}) == STAGE_FINGERPRINT_PROFILE.fingerprint(root)

    def test_validation_runner_resolves_to_source_config_profile(self, tmp_path):
        root = _write_tree(tmp_path / "workspace", {"src/main.ts": "x", "dist/bundle.js": "b"})
        assert ValidationRunner.source_fingerprint(root) == SOURCE_CONFIG_FINGERPRINT_PROFILE.fingerprint(root)

    def test_empty_trees_converge(self, tmp_path):
        root = _empty_tree(tmp_path / "workspace")
        expected = STAGE_FINGERPRINT_PROFILE.fingerprint(root)
        assert PLANNING_FINGERPRINT_PROFILE.fingerprint(root) == expected
        assert WorkspaceIntegrityService.fingerprint(root) == expected
        assert StageSandboxCopier.fingerprint(root) == expected
        assert ValidationRunner.source_fingerprint(root) == expected


def test_fingerprint_of_missing_root_fails_closed(tmp_path):
    with pytest.raises(OSError):
        workspace_fingerprint_v1(tmp_path / "does-not-exist")
