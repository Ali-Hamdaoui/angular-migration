"""Backend-only migration runner (V2.3 Phase 4).

Executes the proven Transformer workflow without any frontend dependency.

Usage::

    python -m backend.migration_runner \\
        --source angular11 --target angular21 --mode qualification

The runner drives the QualificationRunner chain (or a single adjacent
transition in ``--mode single``) against a real Angular source workspace and
writes ``migration-result.json`` containing the run id, stage list, executed
commands, evidence references, failures, repairs, and final status.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

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
    return parser.parse_args(argv)


def _major(family: str) -> int:
    return int(family.removeprefix("angular").removeprefix("-").removesuffix(".x"))


def _require_source_dir(args: argparse.Namespace) -> Path:
    if args.source_dir is None:
        raise SystemExit("--source-dir is required for backend-only execution")
    path = Path(args.source_dir).resolve()
    if not path.is_dir() or not (path / "package.json").is_file():
        raise SystemExit(f"source workspace has no package.json: {path}")
    return path


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    source_major = _major(args.source)
    target_major = _major(args.target)
    if source_major >= target_major:
        raise SystemExit("--source major must be lower than --target major")
    source_dir = _require_source_dir(args)
    if args.mode == "qualification":
        from app.services.qualification_runner import QualificationRunner

        result = QualificationRunner().run_qualification(
            source_dir=source_dir,
            source_major=source_major,
            target_major=target_major,
            evidence_root=args.evidence_root,
            run_id=args.run_id,
        )
        payload = result.migration_result()
        if not args.run_id:
            payload["run_id"] = result.run_id
    else:
        from app.services.qualification_runner import QualificationRunner

        runner = QualificationRunner()
        evidence = runner._run_transition(
            source=source_dir,
            source_major=source_major,
            target_major=target_major,
            workdir=source_dir.parent / f".qualification-{source_major}-{target_major}",
            evidence_path=(args.evidence_root or source_dir.parent / "qualification-evidence")
            / f"stages/{source_major}-{target_major}/stage-evidence.json",
        )
        payload = {
            "run_id": args.run_id or f"single-{source_major}-{target_major}",
            "mode": "single",
            "stage": f"{source_major}->{target_major}",
            "final_status": "completed" if evidence.promotion.get("status") == "promoted" else "failed",
            "stage_evidence": evidence.stage_evidence(),
        }
    output = args.output.resolve()
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"migration-result written to {output}", flush=True)
    print(f"final status: {payload['final_status']}", flush=True)
    return 0 if payload["final_status"] in {"completed", "promoted"} else 1


if __name__ == "__main__":
    raise SystemExit(main())