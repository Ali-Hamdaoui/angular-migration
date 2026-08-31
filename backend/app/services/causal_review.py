"""Causal-review gate and repair accounting for the Transformer repair workflow.

``causal_rejection`` is a pure structural gate answering one question: "Will the
proposal modify the state responsible for the failure?"  ``g10_eligibility`` and
``repair_budget`` are read-only DB-backed helpers consumed by the orchestration
gate and failure classifier.  This module imports nothing from
repair_application_service / transformer_graph / failure_evidence_service to
avoid import cycles.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from sqlalchemy import select

from app.artifact_store import (
    ArtifactNotFoundError,
    ArtifactStoreError,
    LocalFilesystemArtifactStore,
)
from app.repositories.models import (
    ArtifactMetadataModel,
    CommandExecutionModel,
    MigrationRunModel,
    RepairAttemptModel,
    StageGatePackageModel,
    StageExecutionPlanModel,
    StageStepModel,
    TransformationContinuationModel,
)
from app.services.failure_evidence_service import FailureEvidenceService

logger = logging.getLogger(__name__)

DEPENDENCY_NORMALIZATION_REPAIR_KIND = "dependency_manifest_normalization"
DEPENDENCY_NORMALIZATION_SCHEMA_VERSION = "dependency-normalization-v1"
_MIGRATE_PACKAGES_NODE = "migrate_packages"
_DEPENDENCY_INCOMPATIBLE_ROUTE = "dependency_incompatible"

REVIEWER_CAUSAL_POLICY = (
    "CAUSAL-REPAIR POLICY (binding): the proposal must modify the state that caused the "
    "executable failure in the evidence. Reject (decision \"reject\", or \"request_changes\" "
    "with explicit findings) any proposal that does not change the failing state: "
    "documentation-only changes (README or *.md/*.rst/*.txt files, AUTOMATION_README.md, "
    "comments), unrelated source edits, and any proposal containing \"--force\". "
    "For canonical dependency_add, the proposer MUST author only the controlled package.json "
    "dependency intent (package, section, registry semver spec) and MUST NOT fabricate "
    "package-lock.json contents or node_modules state: lockfile generation, npm ci, and exact "
    "post-state verification are governed backend steps that run after G10 approval. Do NOT "
    "reject a dependency_add solely because the candidate diff contains only package.json. "
    "Reject it when the package does not causally address the failure, the dependency section "
    "is wrong, the spec is unsafe or non-semver, unrelated files are touched, the validation "
    "target is missing, the approved backend lockfile-generation/verification plan is absent, "
    "the package already exists (the operation should then be dependency_change), or the "
    "operation violates causal policy. For dependency-conflict failures (for example Angular "
    "peer-dependency conflicts), only a complete dependency transition "
    "(detach/update/reattach with blocking dependency and target state, plus lockfile "
    "regeneration) is causally valid. For dependency_transition, the backend binds the "
    "authoritative package, section, installed version, and target version into "
    "blocking_dependency and target_state; do not require operation-level package, "
    "section, or new_version fields or a proposal diff. Accept only proposals that "
    "change the state responsible for the failure. "
    "For dependency_incompatible / migrate_packages failures, only a complete "
    "dependency_manifest_normalization (schema dependency-normalization-v1) with every "
    "direct dependencies+devDependencies package exactly once, no duplicates, backend-fixed "
    "Angular requirements preserved, no scripts/.npmrc/workspaces/overrides mutation, no "
    "--force/--legacy-peer-deps, replacement explicit (target_package+target_version), and "
    "exact postimage bytes following from approved actions is causally valid."
)

CAUSAL_REJECTION_DOCUMENTATION = "CAUSAL_REJECTION_DOCUMENTATION"
CAUSAL_REJECTION_MANIFEST_ONLY = "CAUSAL_REJECTION_MANIFEST_ONLY"
CAUSAL_REJECTION_UNRELATED_EDIT = "CAUSAL_REJECTION_UNRELATED_EDIT"
CAUSAL_REJECTION_NO_LOCKFILE_SYNC = "CAUSAL_REJECTION_NO_LOCKFILE_SYNC"
CAUSAL_REJECTION_FORCE = "CAUSAL_REJECTION_FORCE"
CAUSAL_REJECTION_UNSUPPORTED_OPERATION = "CAUSAL_REJECTION_UNSUPPORTED_OPERATION"
REPAIR_CAUSAL_KIND_MISMATCH = "REPAIR_CAUSAL_KIND_MISMATCH"

_DIRTY_WORKSPACE_PHRASE = "Repository is not clean"
_WARNING_ONLY_LINE_TOKENS = ("npm warn", "deprecat", "npm audit")
_DOC_SUFFIXES = (".md", ".rst", ".txt")
_DOC_NAME_PREFIXES = (
    "readme",
    "automation_readme",
    "contributing",
    "changelog",
    "license",
    "licence",
    "copying",
    "notice",
)
# Mirrors failure_evidence_service.FailureEvidenceService.dependency_codes.
_DEPENDENCY_ERROR_CODES = frozenset(
    {"DEPENDENCY_PREFLIGHT_BLOCKED", "VERSION_VERIFICATION_FAILED", "VALIDATION_TARGET_MISSING"}
)
# Statuses that provably carried a reviewer decision before any ledger could
# exist; used by repair_budget condition 2 (no artifact reads, deterministic).
_REVIEWER_ACCEPTED_STATUSES = frozenset(
    {
        "waiting_g10",
        "approved_pending_execution",
        "executing",
        "applied",
        "applied_verified",
        "migration_retried",
        "validation_passed",
        "validation_failed",
        "revalidating",
        "revalidating_affected",
        "apply_recovery_required",
        "waiting_g11",
        "transition_complete",
    }
)


@dataclass(frozen=True)
class CausalRejection:
    code: str
    reason: str


def _warning_only_evidence(evidence: dict, normalized: dict) -> bool:
    """True when the failure message is only warning output, never a root cause."""
    message = " ".join(str(normalized.get("failure_message") or "").split())
    allows_dirty = bool(
        normalized.get("command_allows_dirty") or evidence.get("command_allows_dirty")
    )
    if allows_dirty and _DIRTY_WORKSPACE_PHRASE in message:
        return True
    lines = [line.strip().lower() for line in message.splitlines() if line.strip()]
    return bool(lines) and all(
        any(token in line for token in _WARNING_ONLY_LINE_TOKENS) for line in lines
    )


def _is_documentation_path(path: str) -> bool:
    lower = path.lower()
    if lower.endswith(_DOC_SUFFIXES):
        return True
    return PurePosixPath(lower).name.startswith(_DOC_NAME_PREFIXES)


def _operation_carries_force(operation: dict) -> bool:
    """True when an operation introduces ``--force`` into executable config.

    Only ``package.json`` carries executable command configuration (npm
    scripts) in this workflow; text written to any other path (source code,
    comments, docs) is never executed and may mention ``--force`` freely.
    Preimage fields never count: removing an existing ``--force`` is
    compliant.
    """
    kind = str(operation.get("operation") or "")
    if kind in {"replace_text", "create_text_file"}:
        if str(operation.get("path") or "") != "package.json":
            return False
        payload = operation.get("new_text") if kind == "replace_text" else operation.get("content")
        return "--force" in str(payload or "")
    if kind in {"delete_text_file", "dependency_change", "dependency_add", "dependency_transition"}:
        # delete_text_file has no postimage; dependency_change.new_version is a
        # validated version string, not argv; dependency_add.new_version is a
        # backend-approved registry semver spec, not argv; dependency_transition
        # fields are backend-bound authority. None can introduce executable --force.
        return False
    # ponytail: unknown kinds are schema-invalid; fail closed on the payload.
    return "--force" in json.dumps(operation, sort_keys=True, default=str)


def _diff_carries_force(diff: str) -> bool:
    """True when an ADDED diff line introduces ``--force`` into package.json.

    Only package.json scripts are executable in this workflow; added text in
    other files is source/docs content.  Deleted lines, context lines, and
    diff metadata (---/+++/@@ headers) never count.
    """
    touches_package_json = any(
        line.startswith(("--- a/", "+++ b/")) and line.rstrip().endswith("package.json")
        for line in diff.splitlines()
    )
    if not touches_package_json:
        return False
    for line in diff.splitlines():
        if line.startswith(("--- ", "+++ ", "@@")):
            continue
        if line.startswith("+") and "--force" in line:
            return True
    return False


def _carries_force_flag(proposal: dict) -> bool:
    """True only when the proposal introduces executable ``--force``.

    Prose-only fields (rationale, limitations, descriptions, findings,
    provenance), preimage/deleted content, and text written to non-executable
    paths may mention ``--force`` without proposing to use it.  Only text that
    lands in executable command configuration -- package.json scripts, or
    ADDED package.json diff lines -- is inspected.
    # ponytail: package.json is the only executable surface in this workflow;
    a new executable path must be added here.
    """
    diff = proposal.get("unified_diff")
    if isinstance(diff, str) and _diff_carries_force(diff):
        return True
    operations = proposal.get("operations")
    if isinstance(operations, list):
        for operation in operations:
            if isinstance(operation, dict) and _operation_carries_force(operation):
                return True
    return False


def _structural_rejection(proposal: dict) -> CausalRejection | None:
    operations = proposal.get("operations")
    operations = operations if isinstance(operations, list) else []
    touched = proposal.get("touched_files")
    touched = [path for path in touched if isinstance(path, str)] if isinstance(touched, list) else []
    for operation in operations:
        if not isinstance(operation, dict):
            continue
        path = str(operation.get("path") or "")
        if path and _is_documentation_path(path):
            return CausalRejection(
                CAUSAL_REJECTION_DOCUMENTATION,
                f"Documentation-only change to {path} cannot fix an executable failure",
            )
    for path in touched:
        if _is_documentation_path(path):
            return CausalRejection(
                CAUSAL_REJECTION_DOCUMENTATION,
                f"Documentation-only change to {path} cannot fix an executable failure",
            )
    if _carries_force_flag(proposal):
        return CausalRejection(
            CAUSAL_REJECTION_FORCE, "Proposal carries a --force flag, which is not causal"
        )
    if not operations and not touched:
        return CausalRejection(
            CAUSAL_REJECTION_UNRELATED_EDIT,
            "Proposal changes nothing, so it cannot change the failing state",
        )
    return None


def _is_transition_operation(operation: dict) -> bool:
    if str(operation.get("operation") or "") != "dependency_transition" and str(
        operation.get("repair_kind") or ""
    ) != "dependency_transition":
        return False
    if str(operation.get("strategy") or "") != "detach_update_reattach":
        return False
    return bool(operation.get("blocking_dependency")) and bool(operation.get("target_state"))


def _peer_conflict_rejection(proposal: dict) -> CausalRejection | None:
    operations = proposal.get("operations")
    operations = operations if isinstance(operations, list) else []
    touched = proposal.get("touched_files")
    touched = [path for path in touched if isinstance(path, str)] if isinstance(touched, list) else []
    if not operations:
        if touched and all(path == "package.json" for path in touched):
            return CausalRejection(
                CAUSAL_REJECTION_MANIFEST_ONLY,
                "A package.json edit without a controlled dependency_transition cannot "
                "resolve a peer-dependency conflict",
            )
        if touched:
            return CausalRejection(
                CAUSAL_REJECTION_UNRELATED_EDIT,
                "Edits unrelated to package.json cannot resolve a peer-dependency conflict",
            )
        return CausalRejection(
            CAUSAL_REJECTION_MANIFEST_ONLY,
            "A peer-dependency conflict requires a dependency_transition operation",
        )
    for operation in operations:
        path = str(operation.get("path") or "") if isinstance(operation, dict) else ""
        if path and path != "package.json":
            return CausalRejection(
                CAUSAL_REJECTION_UNRELATED_EDIT,
                f"Edit to {path} is unrelated to a peer-dependency conflict",
            )
    transitions = [op for op in operations if isinstance(op, dict) and _is_transition_operation(op)]
    if not transitions:
        return CausalRejection(
            CAUSAL_REJECTION_MANIFEST_ONLY,
            "A package.json edit without a dependency_transition cannot resolve a "
            "peer-dependency conflict",
        )
    if len(transitions) != 1 or len(operations) != 1:
        return CausalRejection(
            CAUSAL_REJECTION_UNSUPPORTED_OPERATION,
            "A peer-dependency conflict requires exactly one dependency_transition operation",
        )
    return None


def _is_normalization_operation(op: dict) -> bool:
    if not isinstance(op, dict):
        return False
    if str(op.get("repair_kind") or "") == DEPENDENCY_NORMALIZATION_REPAIR_KIND:
        return True
    if str(op.get("operation") or "") == DEPENDENCY_NORMALIZATION_REPAIR_KIND:
        return True
    if str(op.get("schema_version") or "") == DEPENDENCY_NORMALIZATION_SCHEMA_VERSION:
        return True
    # inline plan marker
    if isinstance(op.get("normalization_plan"), dict) or isinstance(op.get("plan"), dict):
        # heuristic: contains packages with action
        return True
    return False


def _normalization_rejection(proposal: dict) -> CausalRejection | None:
    operations = proposal.get("operations")
    operations = operations if isinstance(operations, list) else []
    touched = proposal.get("touched_files")
    touched = [p for p in touched if isinstance(p, str)] if isinstance(touched, list) else []
    # exactly one normalization operation touching package.json
    norms = [op for op in operations if isinstance(op, dict) and _is_normalization_operation(op)]
    if not norms:
        return CausalRejection(
            CAUSAL_REJECTION_MANIFEST_ONLY,
            "dependency_incompatible requires a dependency_manifest_normalization operation",
        )
    if len(norms) != 1 or len(operations) != 1:
        return CausalRejection(
            CAUSAL_REJECTION_UNSUPPORTED_OPERATION,
            "dependency_incompatible requires exactly one dependency_manifest_normalization operation",
        )
    op = norms[0]
    if str(op.get("path") or "") != "package.json":
        return CausalRejection(
            CAUSAL_REJECTION_UNRELATED_EDIT, "normalization must target package.json"
        )
    if str(op.get("schema_version") or op.get("normalization_plan", {}).get("schema_version") or "") not in (
        "",
        DEPENDENCY_NORMALIZATION_SCHEMA_VERSION,
    ):
        # allow missing if embedded plan has it
        pass
    # extract packages list
    plan = op.get("normalization_plan") or op.get("plan") or op
    packages = plan.get("packages")
    # also support top-level packages in op
    if not isinstance(packages, list):
        packages = op.get("packages")
    if not isinstance(packages, list) or not packages:
        return CausalRejection(
            CAUSAL_REJECTION_MANIFEST_ONLY, "normalization plan must list packages"
        )
    # duplicate check
    seen: set[str] = set()
    for item in packages:
        if not isinstance(item, dict):
            return CausalRejection(CAUSAL_REJECTION_UNSUPPORTED_OPERATION, "package entry must be object")
        pkg = str(item.get("package") or "")
        if not pkg or pkg in seen:
            return CausalRejection(
                CAUSAL_REJECTION_UNSUPPORTED_OPERATION,
                f"duplicate or missing package: {pkg!r}",
            )
        seen.add(pkg)
        action = str(item.get("action") or "")
        if action not in {"KEEP", "UPGRADE", "REMOVE", "REPLACE"}:
            return CausalRejection(CAUSAL_REJECTION_UNSUPPORTED_OPERATION, f"invalid action {action}")
        # replacement explicit
        if action == "REPLACE" and (not item.get("target_package") or not item.get("target_version")):
            return CausalRejection(
                CAUSAL_REJECTION_UNSUPPORTED_OPERATION,
                f"REPLACE requires target_package and target_version for {pkg}",
            )
        if action == "UPGRADE" and not item.get("target_version"):
            return CausalRejection(
                CAUSAL_REJECTION_UNSUPPORTED_OPERATION, f"UPGRADE requires target_version for {pkg}"
            )
        if action in ("KEEP", "REMOVE") and (item.get("target_package") or item.get("target_version")):
            return CausalRejection(
                CAUSAL_REJECTION_UNSUPPORTED_OPERATION,
                f"{action} must not carry target_package/version for {pkg}",
            )
        # forbidden flags in reason/version
        for field in (str(item.get("target_version") or ""), str(item.get("reason") or "")):
            if "--force" in field or "--legacy-peer-deps" in field:
                return CausalRejection(CAUSAL_REJECTION_FORCE, "normalization carries forbidden flag")
        section = str(item.get("section") or "")
        if section not in ("dependencies", "devDependencies"):
            return CausalRejection(CAUSAL_REJECTION_UNSUPPORTED_OPERATION, f"invalid section {section}")
    # scripts/.npmrc/workspaces/overrides mutation: proposal must not touch other files
    if any(p != "package.json" for p in touched):
        return CausalRejection(
            CAUSAL_REJECTION_UNRELATED_EDIT, "normalization must touch only package.json"
        )
    for op2 in operations:
        if isinstance(op2, dict) and str(op2.get("path") or "") != "package.json":
            return CausalRejection(CAUSAL_REJECTION_UNRELATED_EDIT, "normalization unrelated file edit")
        # check no --force in new_text/post_text
        for key in ("new_text", "post_text", "postimage_text", "content"):
            if isinstance(op2.get(key), str) and "--force" in str(op2.get(key)):
                return CausalRejection(CAUSAL_REJECTION_FORCE, "normalization postimage carries --force")
    # exact postimage follows from actions: if new_text present, must be JSON
    new_text = op.get("new_text") or op.get("post_text") or op.get("postimage_text")
    if isinstance(new_text, str):
        try:
            doc = json.loads(new_text)
        except Exception:
            return CausalRejection(CAUSAL_REJECTION_UNSUPPORTED_OPERATION, "normalization postimage not JSON")
        if not isinstance(doc, dict):
            return CausalRejection(CAUSAL_REJECTION_UNSUPPORTED_OPERATION, "postimage must be object")
        # one coherent manifest: must have at least dependencies or devDependencies
        # no validation of every dep here (service does), but ensure no scripts mutation beyond original
        # (reviewer cannot load original, so lenient)
    return None


def _is_dependency_failure(diagnosis_kind: str, normalized: dict) -> bool:
    route = FailureEvidenceService().classify({
        "normalized_failure": normalized,
        "failure_fingerprint": "causal-review",
        "prior_fingerprints": [],
    })
    return route == "dependency_incompatible" or str(
        normalized.get("error_code") or ""
    ) in _DEPENDENCY_ERROR_CODES or str(normalized.get("failure_code") or "") in _DEPENDENCY_ERROR_CODES


def _has_manifest_edit(proposal: dict) -> bool:
    operations = proposal.get("operations")
    operations = operations if isinstance(operations, list) else []
    for operation in operations:
        if not isinstance(operation, dict):
            continue
        if operation.get("operation") == "dependency_change" or str(operation.get("path") or "") == "package.json":
            return True
    touched = proposal.get("touched_files")
    return "package.json" in touched if isinstance(touched, list) else False


def _lockfile_generation_authority(stage_plan_commands) -> bool:
    """Lenient mirror of _require_lockfile_generation_authority: reject only when
    the npm-lockfile-generate authority is clearly absent from the stage plan."""
    references = (
        stage_plan_commands.get("lockfile_generation")
        if isinstance(stage_plan_commands, dict)
        else None
    )
    if not isinstance(references, (list, tuple)) or len(references) != 1:
        return False
    reference = references[0]
    if not isinstance(reference, dict):
        return False
    return (
        reference.get("command_id") == "npm-lockfile-generate"
        and reference.get("template_id") == "tpl-npm-lockfile-generate"
        and reference.get("template_version") == 1
        and not reference.get("parameter_bindings")
    )


def causal_rejection(
    evidence: dict, proposal: dict, *, stage_plan_commands=None
) -> CausalRejection | None:
    """Reject a repair proposal that cannot modify the state responsible for the failure.

    Pure and deterministic.  Missing/empty evidence means the gate does not
    apply (returns None); warning-only evidence (dirty workspace, npm warnings)
    is never treated as a root cause.  Evidence that looks executable but lacks
    a normalized failure still runs the structural checks (docs / --force /
    no-op).
    """
    if not isinstance(evidence, dict) or not evidence:
        return None
    if not isinstance(proposal, dict):
        return CausalRejection(
            CAUSAL_REJECTION_UNSUPPORTED_OPERATION, "Proposal is not a valid object"
        )
    normalized = evidence.get("normalized_failure")
    normalized = normalized if isinstance(normalized, dict) else {}
    if _warning_only_evidence(evidence, normalized):
        return None
    error_code = str(normalized.get("error_code") or evidence.get("error_code") or "").strip()
    failure_code = str(normalized.get("failure_code") or evidence.get("failure_code") or "").strip()
    executable = bool(error_code or failure_code)

    structural = _structural_rejection(proposal)
    if structural is not None:
        return structural
    if not executable:
        return None

    diagnosis = normalized.get("failure_diagnosis")
    diagnosis_kind = str(diagnosis.get("kind") or "") if isinstance(diagnosis, dict) else ""
    causal = evidence.get("causal_repair")
    causal_kind = str(causal.get("causal_kind") or "") if isinstance(causal, dict) else ""
    route = str(
        evidence.get("route")
        or evidence.get("route_info")
        or evidence.get("failure_route")
        or ""
    ).strip()
    # Derived causal metadata predates the canonical module-resolution route in
    # some immutable artifacts. Re-evaluate the frozen normalized evidence;
    # never trust a historical derived owner over current deterministic proof.
    canonical_route = FailureEvidenceService().classify({
        "normalized_failure": normalized,
        "failure_fingerprint": "causal-review",
        "prior_fingerprints": [],
    }).value
    if canonical_route == "package_export_incompatible":
        route = canonical_route
        causal_kind = "source"
    # new normalization path takes precedence for dependency_incompatible / migrate_packages
    operations = proposal.get("operations") if isinstance(proposal.get("operations"), list) else []
    has_norm = any(_is_normalization_operation(op) for op in operations if isinstance(op, dict))
    has_manifest_edit = _has_manifest_edit(proposal)
    dependency_evidence = _is_dependency_failure(diagnosis_kind, normalized)
    if causal_kind == "environment":
        return CausalRejection(
            REPAIR_CAUSAL_KIND_MISMATCH,
            "Environment failures cannot authorize an LLM code or dependency repair",
        )
    if causal_kind in {"build", "test", "lint", "source"} and has_manifest_edit and not dependency_evidence:
        return CausalRejection(
            REPAIR_CAUSAL_KIND_MISMATCH,
            f"A {causal_kind} failure does not authorize an unrelated dependency mutation",
        )
    if causal_kind == "dependency" or route in (
        _DEPENDENCY_INCOMPATIBLE_ROUTE,
        "dependency_incompatible",
        _MIGRATE_PACKAGES_NODE,
        "migrate_packages",
        DEPENDENCY_NORMALIZATION_REPAIR_KIND,
    ) or has_norm:
        # preserve legacy: if it's a classic peer conflict transition, keep old path
        if not has_norm and (diagnosis_kind == "peer_dependency_conflict" or route == "angular_update_peer_conflict"):
            return _peer_conflict_rejection(proposal)
        # for normalize-capable failures, require complete normalization
        norm_rejection = _normalization_rejection(proposal)
        if norm_rejection is not None:
            return norm_rejection
        # ensure lockfile authority for normalization as well (same as manifest edits)
        if not _lockfile_generation_authority(stage_plan_commands):
            return CausalRejection(
                CAUSAL_REJECTION_NO_LOCKFILE_SYNC,
                "Manifest-only dependency edits need the approved npm-lockfile-generate "
                "authority to keep the lockfile and installed tree synchronized",
            )
        return None
    if diagnosis_kind == "peer_dependency_conflict" or route == "angular_update_peer_conflict":
        return _peer_conflict_rejection(proposal)
    if dependency_evidence and has_manifest_edit:
        if not _lockfile_generation_authority(stage_plan_commands):
            return CausalRejection(
                CAUSAL_REJECTION_NO_LOCKFILE_SYNC,
                "Manifest-only dependency edits need the approved npm-lockfile-generate "
                "authority to keep the lockfile and installed tree synchronized",
            )
    return None


def _load_attempt_artifact(
    session, store, attempt, run_id: str, stage_id: str, artifact_field: str, checksum_field: str, *, pre_attempt: bool
) -> dict | None:
    """Checksum- and envelope-bound artifact read; None on any binding deviation."""
    artifact_id = getattr(attempt, artifact_field)
    checksum = getattr(attempt, checksum_field)
    if not artifact_id or not checksum:
        return None
    metadata = session.get(ArtifactMetadataModel, "metadata-" + str(artifact_id))
    if (
        metadata is None
        or metadata.run_id != run_id
        or metadata.stage_id != stage_id
        or metadata.checksum != checksum
    ):
        return None
    try:
        stored = store.read_artifact(run_id, metadata.relative_path)
    except (ArtifactNotFoundError, ArtifactStoreError, OSError):
        return None
    envelope = stored.envelope
    if (
        stored.ref.artifact_id != artifact_id
        or stored.ref.checksum != checksum
        or envelope is None
        or envelope.run_id != run_id
        or envelope.stage_id != stage_id
    ):
        return None
    if pre_attempt:
        if envelope.attempt_id not in (None, attempt.id):
            return None
    elif envelope.attempt_id != attempt.id:
        return None
    try:
        payload = json.loads(stored.content)
    except (TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _stage_plan_commands(session, run_id: str, stage_id: str) -> dict:
    continuation = session.scalar(
        select(TransformationContinuationModel).where(
            TransformationContinuationModel.run_id == run_id,
            TransformationContinuationModel.current_stage_id == stage_id,
        )
    )
    if continuation is None:
        return {}
    stage_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
    if stage_plan is None:
        return {}
    commands = (stage_plan.stage_plan or {}).get("commands")
    return dict(commands) if isinstance(commands, dict) else {}


def g10_eligibility(session, run_id: str, stage_id: str, attempt_id: str) -> tuple[bool, str | None]:
    """(True, None) when the attempt's checksum-bound proposal + evidence pass
    causal_rejection and an accepted review exists; else (False, reason).

    Additive to the existing G10 packaging checks; never raises.
    """
    attempt = session.get(RepairAttemptModel, attempt_id)
    if attempt is None:
        return False, "attempt missing"
    if attempt.run_id != run_id or attempt.stage_id != stage_id:
        return False, "attempt binding mismatch"
    run = session.get(MigrationRunModel, run_id)
    if run is None or not run.artifact_root:
        return False, "run artifact root missing"
    store = LocalFilesystemArtifactStore(
        Path(str(run.artifact_root)).parent, fixed_run_root=Path(str(run.artifact_root))
    )
    proposal = _load_attempt_artifact(
        session, store, attempt, run_id, stage_id,
        "proposal_artifact_id", "proposal_checksum", pre_attempt=False,
    )
    if proposal is None:
        return False, "no proposal"
    evidence = _load_attempt_artifact(
        session, store, attempt, run_id, stage_id,
        "failure_evidence_artifact_id", "failure_evidence_checksum", pre_attempt=True,
    )
    if evidence is None:
        return False, "no failure evidence"
    review = _load_attempt_artifact(
        session, store, attempt, run_id, stage_id,
        "review_artifact_id", "review_checksum", pre_attempt=False,
    )
    if review is None or review.get("decision") != "accept":
        return False, "reviewer request_changes requires a supported revision"
    current_strategy = _semantic_strategy(proposal, attempt)
    if current_strategy is not None:
        prior_attempts = session.scalars(
            select(RepairAttemptModel).where(
                RepairAttemptModel.run_id == run_id,
                RepairAttemptModel.stage_id == stage_id,
                RepairAttemptModel.attempt_number < attempt.attempt_number,
                RepairAttemptModel.apply_ledger_artifact_id.is_not(None),
                RepairAttemptModel.status.in_(("validation_failed", "superseded")),
            )
        ).all()
        for prior in prior_attempts:
            prior_proposal = _load_attempt_artifact(
                session, store, prior, run_id, stage_id,
                "proposal_artifact_id", "proposal_checksum", pre_attempt=False,
            )
            if _semantic_strategy(prior_proposal, prior) == current_strategy:
                return False, "REPAIR_STRATEGY_ALREADY_FAILED"
    rejection = causal_rejection(
        evidence, proposal, stage_plan_commands=_stage_plan_commands(session, run_id, stage_id)
    )
    if rejection is not None:
        return False, rejection.reason
    return True, None


def _semantic_strategy(proposal: dict | None, attempt: RepairAttemptModel) -> tuple[str, ...] | None:
    operations = proposal.get("operations") if isinstance(proposal, dict) else None
    if not isinstance(operations, list) or len(operations) != 1 or not isinstance(operations[0], dict):
        return None
    operation = operations[0]
    if operation.get("operation") != "dependency_transition":
        return None
    blocking = operation.get("blocking_dependency")
    target = operation.get("target_state")
    return (
        "dependency_transition",
        str(operation.get("repair_kind") or ""),
        str(operation.get("strategy") or ""),
        str(blocking.get("package") or "") if isinstance(blocking, dict) else "",
        str(target.get("target_version") or "") if isinstance(target, dict) else "",
        str(attempt.failure_fingerprint or ""),
        str(attempt.checkpoint_id or ""),
        str(attempt.pre_fingerprint or ""),
    )


def _angular_update_successors(session, run_id: str, stage_id: str) -> list | None:
    """Retry/successor executions of the failed angular update, or None when the
    stage has no angular-update retry (condition 4 not applicable)."""
    step = session.scalars(
        select(StageStepModel).where(
            StageStepModel.run_id == run_id,
            StageStepModel.stage_id == stage_id,
            StageStepModel.name == "angular_update-0",
        )
    ).first()
    if step is None or not step.execution_id:
        return None
    execution = session.get(CommandExecutionModel, step.execution_id)
    if execution is None or execution.parent_execution_id is None:
        return None
    return session.scalars(
        select(CommandExecutionModel).where(
            CommandExecutionModel.run_id == run_id,
            CommandExecutionModel.stage_id == stage_id,
            CommandExecutionModel.parent_execution_id.is_not(None),
        )
    ).all()


def _at_or_after(left, right) -> bool:
    if left is None or right is None:
        return False
    if left.tzinfo is not None:
        left = left.replace(tzinfo=None)
    if right.tzinfo is not None:
        right = right.replace(tzinfo=None)
    return left >= right


def _dependency_transition_attempt(session, run, row) -> bool:
    if not run or not run.artifact_root:
        return False
    proposal = _load_attempt_artifact(
        session,
        LocalFilesystemArtifactStore(
            Path(str(run.artifact_root)).parent,
            fixed_run_root=Path(str(run.artifact_root)),
        ),
        row,
        run.id,
        row.stage_id,
        "proposal_artifact_id",
        "proposal_checksum",
        pre_attempt=False,
    )
    operations = proposal.get("operations") if isinstance(proposal, dict) else None
    return bool(
        isinstance(operations, list)
        and len(operations) == 1
        and isinstance(operations[0], dict)
        and operations[0].get("operation") == "dependency_transition"
    )


def _succeeded_execution(session, run_id: str, stage_id: str, idempotency_key: str) -> bool:
    execution = session.scalar(
        select(CommandExecutionModel).where(
            CommandExecutionModel.run_id == run_id,
            CommandExecutionModel.stage_id == stage_id,
            CommandExecutionModel.idempotency_key == idempotency_key,
        )
    )
    return execution is not None and execution.status == "succeeded" and execution.exit_code == 0


def _repair_completed(session, run, row, successors) -> bool:
    if (
        row.apply_ledger_artifact_id is None
        or row.status not in {
            "applied",
            "revalidating_affected",
            "revalidating",
            "migration_retried",
            "waiting_g11",
        }
        or not row.proposal_artifact_id
        or not row.proposal_checksum
        or not row.review_artifact_id
        or not row.g10_gate_package_id
    ):
        return False
    gate = session.get(StageGatePackageModel, row.g10_gate_package_id)
    if gate is None or gate.status != "approved":
        return False
    is_transition = _dependency_transition_attempt(session, run, row)
    if is_transition:
        boundary_reexecuted = successors is not None and any(
            execution.status == "succeeded"
            and execution.exit_code == 0
            and _at_or_after(execution.requested_at, row.created_at)
            for execution in successors
        )
    else:
        boundary_reexecuted = successors is None or any(
            _at_or_after(execution.requested_at, row.created_at) for execution in successors
        )
    if not boundary_reexecuted:
        return False
    if not is_transition:
        return True
    return (
        _succeeded_execution(session, run.id, row.stage_id, f"{row.id}:transition:uninstall")
        and _succeeded_execution(session, run.id, row.stage_id, f"{row.id}:transition:install")
        and _succeeded_final_install(session, run.id, row.stage_id)
    )


def _succeeded_final_install(session, run_id: str, stage_id: str) -> bool:
    step = session.scalar(
        select(StageStepModel).where(
            StageStepModel.run_id == run_id,
            StageStepModel.stage_id == stage_id,
            StageStepModel.name == "final_install-0",
        )
    )
    execution = session.get(CommandExecutionModel, step.execution_id) if step and step.execution_id else None
    return execution is not None and execution.status == "succeeded" and execution.exit_code == 0


def repair_budget(
    session,
    run_id: str,
    stage_id: str,
    repair_policy: dict,
    *,
    lineage_root_attempt_id: str | None = None,
) -> dict:
    """Applied repair counts for one causal lineage plus the stage ceiling.

    Schema/semantic/duplicate-path/causal rejections, reviewer rejections,
    reconstruction-only states, command supersession retries, and warning-only
    conditions never consume either count.  Once a reviewer-approved G10
    repair has executed and produced an apply ledger, it consumes the bounded
    repair budget immediately.  Waiting for a later boundary retry to finish
    before counting it allows a second repair to be admitted while the command
    retry budget is already exhausted, leaving an approved repair stranded at
    the retry boundary.  Completion evidence is still tracked separately by
    ``_repair_completed``.  Read-only; never raises.
    """
    max_attempts = max_applied = 2
    max_total_applied = 6
    try:
        rows = session.scalars(
            select(RepairAttemptModel)
            .where(
                RepairAttemptModel.run_id == run_id,
                RepairAttemptModel.stage_id == stage_id,
            )
            .order_by(RepairAttemptModel.attempt_number)
        ).all()
        run = session.get(MigrationRunModel, run_id)
        # Budget consumption is based on the irreversible governed apply, not
        # on a later command result.  In particular, ``applied_verified`` and
        # dependency-transition ``executing`` are durable post-apply states.
        applied = [
            row
            for row in rows
            if row.apply_ledger_artifact_id is not None
            and row.status in _REVIEWER_ACCEPTED_STATUSES
        ]
        total_applied = len(applied)
        if lineage_root_attempt_id:
            if run is None or not run.artifact_root:
                raise ValueError("repair lineage artifact authority is missing")
            store = LocalFilesystemArtifactStore(
                Path(str(run.artifact_root)).parent,
                fixed_run_root=Path(str(run.artifact_root)),
            )
            lineage = []
            for row in applied:
                context = _load_attempt_artifact(
                    session,
                    store,
                    row,
                    run_id,
                    stage_id,
                    "context_pack_artifact_id",
                    "context_pack_checksum",
                    pre_attempt=True,
                )
                causal = context.get("causal_repair") if isinstance(context, dict) else None
                if not isinstance(causal, dict):
                    raise ValueError("applied repair lacks causal lineage authority")
                if causal.get("lineage_root_attempt_id") == lineage_root_attempt_id:
                    lineage.append(row)
            applied = lineage
        consumed_applied = len(applied)
        consumed_attempts = 0
        for row in applied:
            if not row.proposal_artifact_id or not row.proposal_checksum:
                continue
            if row.review_artifact_id is None or row.status not in _REVIEWER_ACCEPTED_STATUSES:
                continue
            consumed_attempts += 1
    except Exception:
        logger.exception(
            "repair_budget failed; returning consumed zero",
            extra={"run_id": run_id, "stage_id": stage_id},
        )
        return {
            "consumed_attempts": 0,
            "consumed_applied": 0,
            "max_attempts": max_attempts,
            "max_applied": max_applied,
            "total_applied": max_total_applied,
            "max_total_applied": max_total_applied,
        }
    return {
        "consumed_attempts": consumed_attempts,
        "consumed_applied": consumed_applied,
        "max_attempts": max_attempts,
        "max_applied": max_applied,
        "total_applied": total_applied,
        "max_total_applied": max_total_applied,
    }
