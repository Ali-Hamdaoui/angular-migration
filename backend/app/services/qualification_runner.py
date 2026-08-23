"""Qualification engine (V2.3 Phase 8).

Runs the proven adjacent-major chain ``11 -> 12 -> ... -> 21`` against a real
source workspace, sealing each transition before the next one starts.  Every
transition produces one ``stage-evidence.json`` binding runtime identity,
dependency intent, lock checksum, build/test results, workspace fingerprint,
and the promotion outcome.  No Angular major is hardcoded: the route is
derived from the compatibility catalogue, and the whole engine is generic
stage execution.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


class QualificationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class CommandOutcome:
    command_id: str
    arguments: tuple[str, ...]
    exit_code: int | None
    status: str
    stdout: str
    stderr: str
    stdout_sha256: str
    stderr_sha256: str
    duration_ms: int


@dataclass(frozen=True)
class TransitionEvidence:
    source_major: int
    target_major: int
    source_exact: str
    target_exact: str
    runtime: dict[str, str]
    dependencies: dict[str, object]
    lock_checksum: str | None
    build: dict[str, object]
    test: dict[str, object]
    fingerprint: str
    promotion: dict[str, object]
    commands: tuple[CommandOutcome, ...] = field(default_factory=tuple)

    def stage_evidence(self) -> dict[str, object]:
        return {
            "schema_version": "stage-evidence-v1",
            "transition": f"{self.source_major}->{self.target_major}",
            "source_exact": self.source_exact,
            "target_exact": self.target_exact,
            "runtime": self.runtime,
            "dependencies": self.dependencies,
            "lock_checksum": self.lock_checksum,
            "build": self.build,
            "test": self.test,
            "fingerprint": self.fingerprint,
            "promotion": self.promotion,
            "commands": [
                {
                    "command_id": item.command_id,
                    "exit_code": item.exit_code,
                    "status": item.status,
                    "stdout_sha256": item.stdout_sha256,
                    "stderr_sha256": item.stderr_sha256,
                    "duration_ms": item.duration_ms,
                }
                for item in self.commands
            ],
        }


@dataclass(frozen=True)
class QualificationRunResult:
    source_major: int
    target_major: int
    run_id: str
    stages: tuple[TransitionEvidence, ...]
    status: str
    evidence_dir: str

    def migration_result(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "mode": "qualification",
            "chain": f"{self.source_major}->{self.target_major}",
            "final_status": self.status,
            "stages": [
                {
                    "transition": f"{item.source_major}->{item.target_major}",
                    "status": item.promotion.get("status"),
                    "target_exact": item.target_exact,
                    "stage_evidence": f"stages/{item.source_major}-{item.target_major}/stage-evidence.json",
                }
                for item in self.stages
            ],
            "evidence_dir": self.evidence_dir,
            "completed_at": datetime.now(UTC).isoformat(),
        }


class QualificationRunner:
    """Execute and seal the adjacent-major qualification chain (V2.3 Phase 8).

    Every transition is executed in its own sandbox copy of the sealed
    predecessor; a transition that fails validation never becomes the next
    source (the seal is the promotion authority).  Commands are real governed
    npm/npx invocations; no success path is fabricated.
    """

    def __init__(self, *, command_timeout_seconds: int = 3600) -> None:
        self._timeout = command_timeout_seconds

    def run_qualification(
        self,
        *,
        source_dir: Path,
        source_major: int,
        target_major: int = 21,
        evidence_root: Path | None = None,
        run_id: str | None = None,
    ) -> QualificationRunResult:
        source = Path(source_dir).resolve(strict=True)
        if not (source / "package.json").is_file():
            raise QualificationError("QUALIFICATION_SOURCE_MISSING", "qualification source has no package.json")
        majors = [major for major in range(source_major, target_major)]
        if not majors:
            raise QualificationError("QUALIFICATION_ROUTE_EMPTY", "no adjacent transitions to execute")
        evidence_dir = (evidence_root or source.parent / "qualification-evidence").resolve()
        evidence_dir.mkdir(parents=True, exist_ok=True)
        resolved_run_id = run_id or "qual-" + hashlib.sha256(
            f"{source}:{source_major}:{target_major}".encode()
        ).hexdigest()[:16]
        stages: list[TransitionEvidence] = []
        current = source
        for index, source_major_step in enumerate(majors):
            target_major_step = source_major_step + 1
            transition_dir = evidence_dir / f"stages/{source_major_step}-{target_major_step}"
            transition_dir.mkdir(parents=True, exist_ok=True)
            evidence = self._run_transition(
                source=current,
                source_major=source_major_step,
                target_major=target_major_step,
                workdir=transition_dir / "workspace",
                evidence_path=transition_dir / "stage-evidence.json",
            )
            stages.append(evidence)
            if evidence.promotion.get("status") != "promoted":
                return QualificationRunResult(
                    source_major=source_major,
                    target_major=target_major,
                    run_id=resolved_run_id,
                    stages=tuple(stages),
                    status="failed",
                    evidence_dir=str(evidence_dir),
                )
            current = Path(str(evidence.promotion.get("sealed_source")))
        return QualificationRunResult(
            source_major=source_major,
            target_major=target_major,
            run_id=resolved_run_id,
            stages=tuple(stages),
            status="completed",
            evidence_dir=str(evidence_dir),
        )

    def _run_transition(
        self,
        *,
        source: Path,
        source_major: int,
        target_major: int,
        workdir: Path,
        evidence_path: Path,
    ) -> TransitionEvidence:
        workdir = workdir.resolve()
        if workdir.exists():
            shutil.rmtree(workdir)
        workdir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, workdir)
        try:
            target_exact = self._target_exact(target_major)
        except Exception as error:
            raise QualificationError("QUALIFICATION_TARGET_UNRESOLVED", str(error)) from error
        commands: list[CommandOutcome] = []
        runtime = _runtime_identity()
        # 1. source baseline: same-authority npm ci.
        commands.append(self._run_command(workdir, "npm", ("ci",), command_id="npm-ci-bootstrap"))
        # 2. lock handling: reconcile the existing lock first.
        reconcile = self._run_command(
            workdir, "npm", ("install", "--package-lock-only", "--ignore-scripts"), command_id="npm-lockfile-reconcile"
        )
        commands.append(reconcile)
        if reconcile.exit_code != 0:
            commands.append(
                self._run_command(
                    workdir, "npm", ("install", "--package-lock-only", "--ignore-scripts", "--force"),
                    command_id="npm-lockfile-fresh",
                )
            )
        reproducibility = self._run_command(workdir, "npm", ("ci",), command_id="npm-ci-reproducibility")
        commands.append(reproducibility)
        # 3. target discovery: exact major cohort probes.
        cli_spec = f"@angular/cli@{target_major}"
        core_spec = f"@angular/core@{target_major}"
        discovery_cli = self._run_command(
            workdir, "npx", ("ng", "update", cli_spec, "--dry-run", "--force", "--allow-dirty"),
            command_id="angular-update-discovery-cli",
            env={"NG_DISABLE_VERSION_CHECK": "true"},
        )
        discovery_core = self._run_command(
            workdir, "npx", ("ng", "update", core_spec, "--dry-run", "--force", "--allow-dirty"),
            command_id="angular-update-discovery-core",
            env={"NG_DISABLE_VERSION_CHECK": "true"},
        )
        commands.extend((discovery_cli, discovery_core))
        # 4. angular migrations: CLI first, then core (non-interactive).
        migrate_cli = self._run_command(
            workdir, "npx", ("ng", "update", cli_spec, "--force", "--allow-dirty"),
            command_id="angular-update-cli",
            env={"NG_DISABLE_VERSION_CHECK": "true"},
        )
        migrate_core = self._run_command(
            workdir, "npx", ("ng", "update", core_spec, "--force", "--allow-dirty"),
            command_id="angular-update-core",
            env={"NG_DISABLE_VERSION_CHECK": "true"},
        )
        commands.extend((migrate_cli, migrate_core))
        # 5. freeze dependency authority: final same-authority install + tree proof.
        freeze_install = self._run_command(workdir, "npm", ("ci",), command_id="npm-ci-freeze")
        freeze_tree = self._run_command(workdir, "npm", ("ls", "--depth=0"), command_id="npm-dependency-tree")
        commands.extend((freeze_install, freeze_tree))
        dependencies, lock_checksum = _dependency_state(workdir)
        # 6. clean validation generation: build + test.
        build = self._run_command(workdir, "npm", ("run", "build"), command_id="npm-script-build-production")
        test = self._run_command(workdir, "npm", ("test", "--", "--watch=false", "--browsers=ChromeHeadless"), command_id="npm-script-test-ci")
        commands.extend((build, test))
        fingerprint = _workspace_fingerprint(workdir)
        build_passed = build.exit_code == 0
        test_passed = test.exit_code == 0
        # 7. seal: the validated workspace becomes the next authoritative source.
        sealed_source = str(workdir)
        promotion = {
            "status": "promoted" if build_passed and test_passed else "rejected",
            "candidate_fingerprint": fingerprint,
            "sealed_source": sealed_source,
        }
        evidence = TransitionEvidence(
            source_major=source_major,
            target_major=target_major,
            source_exact=_exact_of(workdir, "@angular/core", fallback=f"{source_major}.0.0"),
            target_exact=target_exact,
            runtime=runtime,
            dependencies=dependencies,
            lock_checksum=lock_checksum,
            build={"status": "PASS" if build_passed else "FAIL", "exit_code": build.exit_code},
            test={"status": "PASS" if test_passed else "FAIL", "exit_code": test.exit_code},
            fingerprint=fingerprint,
            promotion=promotion,
            commands=tuple(commands),
        )
        evidence_path.write_text(json.dumps(evidence.stage_evidence(), indent=2, sort_keys=True), encoding="utf-8")
        return evidence

    def _run_command(
        self,
        workdir: Path,
        executable: str,
        arguments: tuple[str, ...],
        *,
        command_id: str,
        env: dict[str, str] | None = None,
    ) -> CommandOutcome:
        started = datetime.now(UTC)
        environment = dict(env or {})
        resolved = shutil.which(executable)
        if resolved is None:
            return CommandOutcome(
                command_id=command_id,
                arguments=arguments,
                exit_code=None,
                status="failed",
                stdout="",
                stderr=f"executable not found on PATH: {executable}",
                stdout_sha256=_sha256_text(""),
                stderr_sha256=_sha256_text(f"executable not found on PATH: {executable}"),
                duration_ms=0,
            )
        result = subprocess.run(
            [resolved, *arguments],
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=self._timeout,
            env={**__import__("os").environ, **environment},
            check=False,
        )
        duration_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        return CommandOutcome(
            command_id=command_id,
            arguments=arguments,
            exit_code=result.returncode,
            status="succeeded" if result.returncode == 0 else "failed",
            stdout=stdout,
            stderr=stderr,
            stdout_sha256=_sha256_text(stdout),
            stderr_sha256=_sha256_text(stderr),
            duration_ms=duration_ms,
        )

    @staticmethod
    def _target_exact(target_major: int) -> str:
        from app.services.compatibility_catalogue_provider import CompatibilityCatalogueProvider

        entry = CompatibilityCatalogueProvider().load().entry_for(
            f"angular-{target_major - 1}.x", f"angular-{target_major}.x"
        )
        if entry is None:
            raise QualificationError(
                "QUALIFICATION_CATALOGUE_ENTRY_MISSING",
                f"catalogue has no entry for {target_major - 1}->{target_major}",
            )
        return entry.target_angular_exact


# -- helpers ---------------------------------------------------------------


def _sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _runtime_identity() -> dict[str, str]:
    import os
    import platform
    import sys

    def version_of(exe: str) -> str:
        try:
            resolved = shutil.which(exe)
            if resolved is None:
                return "unknown"
            result = subprocess.run([resolved, "--version"], capture_output=True, text=True, timeout=15, check=False)
            return (result.stdout or result.stderr or "").strip().splitlines()[-1] if result.stdout or result.stderr else "unknown"
        except Exception:
            return "unknown"

    return {
        "python": platform.python_version(),
        "node": version_of("node"),
        "npm": version_of("npm"),
        "npx": version_of("npx"),
        "os": platform.system(),
        "arch": platform.machine(),
        "pid": str(os.getpid()),
        "sys_executable": sys.executable,
    }


def _dependency_state(workdir: Path) -> tuple[dict[str, object], str | None]:
    package_json = workdir / "package.json"
    manifest: dict[str, object] = {}
    if package_json.is_file():
        try:
            manifest = json.loads(package_json.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}
    dependencies: dict[str, object] = {}
    for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        dependencies[section] = manifest.get(section) or {}
    lock = workdir / "package-lock.json"
    if not lock.is_file():
        lock = workdir / "npm-shrinkwrap.json"
    return dependencies, _file_sha256(lock)


def _workspace_fingerprint(workdir: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(workdir.rglob("*")):
        if path.is_file() and not any(part in {".git", "node_modules", "dist", ".angular", "coverage"} for part in path.parts):
            digest.update(str(path.relative_to(workdir)).encode("utf-8"))
            file_sha = _file_sha256(path)
            if file_sha is not None:
                digest.update(file_sha.encode("utf-8"))
    return "sha256:" + digest.hexdigest()


def _exact_of(workdir: Path, package: str, *, fallback: str) -> str:
    package_json = workdir / "package.json"
    if package_json.is_file():
        try:
            manifest = json.loads(package_json.read_text(encoding="utf-8"))
            for section in ("dependencies", "devDependencies"):
                version = (manifest.get(section) or {}).get(package)
                if version:
                    return str(version).lstrip("^~")
        except Exception:
            pass
    return fallback