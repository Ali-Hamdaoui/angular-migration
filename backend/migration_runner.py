"""Durable backend-only migration runner.

Usage::

    python -m backend.migration_runner \\
        --source angular11 --target angular21 --mode qualification

The runner never owns process execution.  A persisted run is created through
the normal Factory lifecycle; this command only verifies proven activation and
pumps the existing TransformerWorker until that run reaches a terminal state.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from uuid import uuid4

# Make ``app`` importable when launched as ``python -m backend.migration_runner``
# from the repository root (backend/ is the package that owns app/).
_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="backend.migration_runner", description="Backend-only proven migration execution")
    parser.add_argument("--source", required=True, help="source Angular family, e.g. angular11")
    parser.add_argument("--target", required=True, help="target Angular family, e.g. angular21")
    parser.add_argument("--mode", choices=["qualification", "single"], default="qualification")
    parser.add_argument("--source-dir", type=Path, help="path to the real Angular source workspace")
    parser.add_argument("--evidence-root", type=Path, default=None, help="evidence output root")
    parser.add_argument("--run-id", default=None, help="explicit qualification run id")
    parser.add_argument("--output", type=Path, default=Path("migration-result.json"), help="result output path")
    parser.add_argument("--target-exact", default=None, help="exact target version override for --mode single")
    parser.add_argument("--source-exact", default=None, help="exact source version override for --mode single")
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    return parser.parse_args(argv)


def _major(family: str) -> int:
    return int(family.removeprefix("angular").removeprefix("-").removesuffix(".x"))


def _require_source_dir(args: argparse.Namespace) -> Path | None:
    if args.source_dir is None:
        return None
    path = Path(args.source_dir).resolve()
    if not path.is_dir() or not (path / "package.json").is_file():
        raise SystemExit(f"source workspace has no package.json: {path}")
    return path


def _result(path: Path, payload: dict[str, object]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"migration-result written to {path}", flush=True)
    print(f"final status: {payload['final_status']}", flush=True)
    return 0 if payload["final_status"] in {"completed", "promoted"} else 1


def _failure(code: str, message: str, *, category="unknown") -> dict[str, object]:
    from app.domain.proven_failure import FailureCategory, MigrationFailureEnvelope

    envelope = MigrationFailureEnvelope.create(
        category=FailureCategory(category),
        phase="migration_execution",
        code=code,
        message=message,
    )
    return envelope.model_dump(mode="json")


def _find_run(source_dir: Path | None, source_major: int, target_major: int, mode: str) -> str | None:
    from sqlalchemy import select

    from app.domain.contracts import RunStatus
    from app.repositories.models import MigrationRunModel
    from app.repositories.session import session_scope

    with session_scope() as session:
        runs = list(
            session.scalars(
                select(MigrationRunModel)
                .where(
                    MigrationRunModel.target_version_family.in_({f"angular-{target_major}.x", f"{target_major}.x"}),
                    MigrationRunModel.status.not_in({
                        RunStatus.COMPLETED.value,
                        RunStatus.FAILED.value,
                        RunStatus.CANCELLED.value,
                    }),
                )
                .order_by(MigrationRunModel.created_at.desc())
            )
        )
    def detected_major(run) -> int | None:
        match = re.search(r"(?<!\d)\d+", run.source_version_detected or run.source_angular_version or "")
        return int(match.group()) if match else None

    runs = [run for run in runs if run.source_version_family == f"angular-{source_major}.x" or (run.source_version_family is None and detected_major(run) == source_major)]
    if source_dir is None:
        return runs[0].id if len(runs) == 1 else None
    matches = [run for run in runs if Path(run.source_path or "").resolve() == source_dir]
    preferred = [run for run in matches if (run.target_policy_snapshot or {}).get("migration_mode") == mode]
    if mode == "qualification":
        preferred = [run for run in matches if (run.client_constraints or {}).get("qualification") is True]
    return preferred[0].id if preferred else (matches[0].id if len(matches) == 1 else None)


def _repository_git_sha(root: Path) -> str:
    """Read the checked-out commit identity without launching a process."""
    head = root / ".git" / "HEAD"
    try:
        value = head.read_text(encoding="utf-8").strip()
        if value.startswith("ref: "):
            value = (root / ".git" / value[5:]).read_text(encoding="utf-8").strip()
        return value or "working-tree"
    except OSError:
        return "working-tree"


def _activate_factory_runtime() -> None:
    """Bind this CLI process to the existing Factory runtime authority."""
    from hashlib import sha256

    from app.core.config import get_settings
    from app.core.database import active_revisions
    from app.repositories.session import engine, session_scope
    from app.services.factory_runtime_service import FactoryRuntimeService

    settings = get_settings()
    os.environ.setdefault(
        "FACTORY_RUNTIME_GENERATION",
        f"migration-runner-{os.getpid()}-{uuid4().hex[:12]}",
    )
    os.environ.setdefault("FACTORY_GIT_SHA", _repository_git_sha(settings.platform_repository_root))
    os.environ.setdefault(
        "FACTORY_DATABASE_IDENTITY",
        "sha256:" + sha256((settings.database_url or "").encode("utf-8")).hexdigest(),
    )
    os.environ.setdefault("FACTORY_LAUNCHER_PID", str(os.getpid()))
    runtime = FactoryRuntimeService()
    with session_scope() as session:
        runtime.activate(session, ",".join(active_revisions(engine)))


def _pump(run_id: str, timeout_seconds: int) -> dict[str, object]:
    from sqlalchemy import select

    from app.domain.contracts import RunStatus
    from app.orchestration.transformer_worker import TransformerWorker
    from app.repositories.models import MigrationRunModel, TransformationContinuationModel
    from app.repositories.session import session_scope
    from app.services.proven_activation_gate import ProvenActivationGate

    report = ProvenActivationGate().verify()
    if not report.passed:
        return {
            "run_id": run_id,
            "final_status": "failed",
            "failure": _failure("TRANSFORMER_PROVEN_ACTIVATION_BLOCKED", ", ".join(report.missing), category="environment"),
        }
    try:
        _activate_factory_runtime()
    except Exception as error:
        return {
            "run_id": run_id,
            "final_status": "failed",
            "failure": _failure("FACTORY_RUNTIME_ACTIVATION_FAILED", str(error), category="environment"),
        }
    worker = TransformerWorker(worker_id=f"migration-runner-{os.getpid()}")
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        with session_scope() as session:
            run = session.get(MigrationRunModel, run_id)
            continuation = session.scalar(
                select(TransformationContinuationModel)
                .where(TransformationContinuationModel.run_id == run_id)
                .order_by(TransformationContinuationModel.updated_at.desc())
            )
            if run is None:
                return {"run_id": run_id, "final_status": "failed", "failure": _failure("RUN_NOT_FOUND", "migration run does not exist")}
            if run.status in {item.value for item in RunStatus if item in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}}:
                return {
                    "run_id": run_id,
                    "final_status": "completed" if run.status == RunStatus.COMPLETED.value else "failed",
                    "run_status": run.status,
                    "continuation": continuation.current_node if continuation else None,
                    "failure_code": continuation.last_error_code if continuation else None,
                    "failure": _failure(
                        continuation.last_error_code or "PROVEN_RUN_FAILED",
                        continuation.last_error_message or "proven migration run failed",
                    ) if run.status == RunStatus.FAILED.value else None,
                }
        if not worker.run_once():
            time.sleep(0.25)
    return {
        "run_id": run_id,
        "final_status": "failed",
        "failure": _failure("PROVEN_RUN_TIMEOUT", "proven migration run exceeded the runner timeout", category="environment"),
    }


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    source_major = _major(args.source)
    target_major = _major(args.target)
    if source_major >= target_major:
        raise SystemExit("--source major must be lower than --target major")
    source_dir = _require_source_dir(args)
    output = args.output.resolve()
    run_id = args.run_id or _find_run(source_dir, source_major, target_major, args.mode)
    if run_id is None:
        return _result(output, {
            "run_id": None,
            "mode": args.mode,
            "chain": f"{source_major}->{target_major}",
            "final_status": "failed",
            "failure": _failure(
                "PROVEN_RUN_NOT_INITIALIZED",
                "No persisted run is available; create it through the governed Factory lifecycle before pumping execution.",
            ),
        })
    payload = _pump(run_id, args.timeout_seconds)
    payload.update({"mode": args.mode, "chain": f"{source_major}->{target_major}"})
    return _result(output, payload)


if __name__ == "__main__":
    raise SystemExit(main())
