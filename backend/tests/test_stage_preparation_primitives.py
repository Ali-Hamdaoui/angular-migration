from pathlib import Path
import shutil

import pytest

from app.services.stage_preparation_primitives import StageSandboxCopier


def test_copy_excludes_dependencies_caches_outputs_and_reports_fingerprint(tmp_path: Path):
    source = tmp_path / "baseline"
    target = tmp_path / "stage"
    (source / "src").mkdir(parents=True)
    (source / "node_modules").mkdir()
    (source / ".angular" / "cache").mkdir(parents=True)
    (source / "dist").mkdir()
    (source / "src" / "main.ts").write_text("export const value = 1", encoding="utf-8")
    (source / "node_modules" / "ignored.js").write_text("ignored", encoding="utf-8")
    (source / "dist" / "ignored.js").write_text("ignored", encoding="utf-8")

    report = StageSandboxCopier().copy(source, target)

    assert (target / "src" / "main.ts").read_text(encoding="utf-8") == "export const value = 1"
    assert not (target / "node_modules").exists()
    assert not (target / "dist").exists()
    assert report.fingerprint.startswith("sha256:")
    assert "node_modules" in report.excluded_paths


def test_copy_rejects_target_outside_registered_root(tmp_path: Path):
    source = tmp_path / "baseline"
    source.mkdir()
    try:
        StageSandboxCopier().copy(source, tmp_path / ".." / "outside")
    except ValueError as error:
        assert "containment" in str(error)


@pytest.mark.parametrize("target_name", ("baseline", "baseline/stage"))
def test_copy_rejects_equal_and_descendant_targets_before_copy(tmp_path: Path, target_name: str):
    source = tmp_path / "baseline"
    source.mkdir()
    (source / "package.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="distinct from and outside"):
        StageSandboxCopier().copy(source, tmp_path / target_name)

    assert not (source / "stage").exists()


def test_copy_rejects_a_symlink_in_the_source_tree(tmp_path: Path):
    source = tmp_path / "baseline"
    target = tmp_path / "stage"
    source.mkdir()
    external = tmp_path / "external.txt"
    external.write_text("outside", encoding="utf-8")
    try:
        (source / "linked.txt").symlink_to(external)
    except OSError:
        pytest.skip("symlink creation is unavailable in this environment")

    with pytest.raises(ValueError, match="unsupported symlink"):
        StageSandboxCopier().copy(source, target)

    assert not target.exists()


def test_copy_rejects_a_target_that_contains_the_source(tmp_path: Path):
    source = tmp_path / "baseline"
    source.mkdir()
    (source / "package.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="distinct from and outside"):
        StageSandboxCopier().copy(source, tmp_path, registered_root=tmp_path)


def test_copy_removes_partial_target_when_a_file_copy_fails(tmp_path: Path, monkeypatch):
    source = tmp_path / "baseline"
    target = tmp_path / "stage"
    source.mkdir()
    (source / "first.txt").write_text("first", encoding="utf-8")
    (source / "second.txt").write_text("second", encoding="utf-8")
    original_copy2 = shutil.copy2
    calls = 0

    def fail_on_second_copy(src, dst, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated copy failure")
        return original_copy2(src, dst, *args, **kwargs)

    monkeypatch.setattr(shutil, "copy2", fail_on_second_copy)

    with pytest.raises(OSError, match="simulated copy failure"):
        StageSandboxCopier().copy(source, target)

    assert not target.exists()


def test_copy_atomically_finalizes_without_leaving_a_temporary_sandbox(tmp_path: Path):
    source = tmp_path / "baseline"
    workspace_root = tmp_path / "workspace"
    target = workspace_root / "angular-18-to-19"
    source.mkdir()
    workspace_root.mkdir()
    (source / "package.json").write_text("{}", encoding="utf-8")

    report = StageSandboxCopier().copy_atomically(
        source,
        target,
        registered_root=workspace_root,
    )

    assert Path(report.target) == target
    assert (target / "package.json").read_text(encoding="utf-8") == "{}"
    assert not list(workspace_root.glob(".angular-18-to-19.preparing-*"))
