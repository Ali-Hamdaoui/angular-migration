from pathlib import Path

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
