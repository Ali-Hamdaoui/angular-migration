"""Proven stage execution (V2.3 Phase 2/3).

The proven graph only routes; this service executes.  Each proven node maps
to one deterministic handler that composes the existing proven services
(source baseline, lock resolution, materialization, migration ledger,
validation, promotion, seal, repair).  No node handler invents success: every
handler either performs real work, queues a governed command, or fails closed
with an explicit code.
"""

from __future__ import annotations

import json
import hashlib
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.command_evidence import build_command_execution_evidence
from app.domain.contracts import ArtifactType, WorkflowEventType
from app.domain.proven_failure import (
    FailureCategory,
    MigrationFailureEnvelope,
    envelope_from_execution,
)
from app.domain.transformation import ProvenTransformationNode
from app.domain.command import TRANSFORMATION_COMMAND_CATALOGUE
from app.repositories.models import (
    ArtifactMetadataModel,
    CommandExecutionModel,
    CommandLogChunkModel,
    MigrationPlanModel,
    MigrationRunModel,
    MigrationStageModel,
    StageExecutionPlanModel,
    StageStepModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
)
from app.repositories.session import session_scope
from app.services.proven_activation_gate import ProvenActivationGate
from app.services.command_registry_service import CommandRegistryService
from app.services.package_migration_service import PackageMigrationError, PackageMigrationService
from app.services.proven_stage_tooling_policy import ProvenStageToolingPolicy
from app.services.stage_preparation_primitives import StageSandboxCopier
from app.services.transformer_stage_service import (
    TransformerStageError,
    TransformerStageService,
)
from app.services.transformation_continuation_service import (
    append_continuation_event,
)


class ProvenStageExecutionError(ValueError):
    def __init__(self, code: str, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


#: Node -> successor after a successful deterministic handler.  Handlers that
#: queue a governed command move the continuation to ``waiting_command`` and
#: the terminal command verifier resumes at the next node.
_PROVEN_SUCCESSORS = {
    ProvenTransformationNode.SELECT_RUN_MODE.value: ProvenTransformationNode.PREPARE_STAGE_LAYOUT.value,
    ProvenTransformationNode.PREPARE_STAGE_LAYOUT.value: ProvenTransformationNode.CREATE_SOURCE_BASELINE.value,
    ProvenTransformationNode.CREATE_SOURCE_BASELINE.value: ProvenTransformationNode.CONSTRUCT_DEPENDENCY_INTENT.value,
    ProvenTransformationNode.CONSTRUCT_DEPENDENCY_INTENT.value: ProvenTransformationNode.BIND_NPM_LOCK_AUTHORITY_POLICY.value,
    ProvenTransformationNode.BIND_NPM_LOCK_AUTHORITY_POLICY.value: ProvenTransformationNode.SELECT_SOURCE_LOCK_AUTHORITY.value,
    ProvenTransformationNode.SELECT_SOURCE_LOCK_AUTHORITY.value: ProvenTransformationNode.READ_SOURCE_RESOLVED_LOCK.value,
    ProvenTransformationNode.READ_SOURCE_RESOLVED_LOCK.value: ProvenTransformationNode.PROVE_SOURCE_MANIFEST_VS_RESOLUTION.value,
    ProvenTransformationNode.PROVE_SOURCE_MANIFEST_VS_RESOLUTION.value: ProvenTransformationNode.SOURCE_INSTALL_SAME_AUTHORITY.value,
    ProvenTransformationNode.SOURCE_INSTALL_SAME_AUTHORITY.value: ProvenTransformationNode.SOURCE_TREE.value,
    ProvenTransformationNode.SOURCE_TREE.value: ProvenTransformationNode.SOURCE_VERSION_PROOF.value,
    ProvenTransformationNode.SOURCE_VERSION_PROOF.value: ProvenTransformationNode.SOURCE_BUILD.value,
    ProvenTransformationNode.SOURCE_BUILD.value: ProvenTransformationNode.SOURCE_TEST.value,
    ProvenTransformationNode.SOURCE_TEST.value: ProvenTransformationNode.SOURCE_DIAGNOSTIC_CAPTURE.value,
    ProvenTransformationNode.SOURCE_DIAGNOSTIC_CAPTURE.value: ProvenTransformationNode.FREEZE_SOURCE_BASELINE.value,
    ProvenTransformationNode.FREEZE_SOURCE_BASELINE.value: ProvenTransformationNode.CREATE_DISCOVERY_GENERATION.value,
    ProvenTransformationNode.CREATE_DISCOVERY_GENERATION.value: ProvenTransformationNode.PREPARE_DISCOVERY_TOOLCHAIN.value,
    ProvenTransformationNode.PREPARE_DISCOVERY_TOOLCHAIN.value: ProvenTransformationNode.PROVE_DISCOVERY_CLI_AUTHORITY.value,
    ProvenTransformationNode.PROVE_DISCOVERY_CLI_AUTHORITY.value: ProvenTransformationNode.RUN_DISCOVERY.value,
    ProvenTransformationNode.RUN_DISCOVERY.value: ProvenTransformationNode.ASSESS_DISCOVERY.value,
    ProvenTransformationNode.ASSESS_DISCOVERY.value: ProvenTransformationNode.PERSIST_TARGET_INTENT.value,
    ProvenTransformationNode.PERSIST_TARGET_INTENT.value: ProvenTransformationNode.CREATE_AUTHORITATIVE_TARGET.value,
    ProvenTransformationNode.CREATE_AUTHORITATIVE_TARGET.value: ProvenTransformationNode.APPLY_TARGET_INTENT.value,
    ProvenTransformationNode.APPLY_TARGET_INTENT.value: ProvenTransformationNode.DEPENDENCY_PLAN.value,
    ProvenTransformationNode.DEPENDENCY_PLAN.value: ProvenTransformationNode.SELECT_TARGET_LOCK_AUTHORITY.value,
    ProvenTransformationNode.SELECT_TARGET_LOCK_AUTHORITY.value: ProvenTransformationNode.LOCK_RESOLUTION.value,
    ProvenTransformationNode.LOCK_RESOLUTION.value: ProvenTransformationNode.CREATE_MATERIALIZATION.value,
    ProvenTransformationNode.CREATE_MATERIALIZATION.value: ProvenTransformationNode.TARGET_INSTALL_SAME_AUTHORITY.value,
    ProvenTransformationNode.TARGET_INSTALL_SAME_AUTHORITY.value: ProvenTransformationNode.TARGET_TREE.value,
    ProvenTransformationNode.TARGET_TREE.value: ProvenTransformationNode.TARGET_VERSION_PROOF.value,
    ProvenTransformationNode.TARGET_VERSION_PROOF.value: ProvenTransformationNode.INSPECT_MIGRATION_METADATA.value,
    ProvenTransformationNode.INSPECT_MIGRATION_METADATA.value: ProvenTransformationNode.BUILD_MIGRATION_LEDGER.value,
    ProvenTransformationNode.BUILD_MIGRATION_LEDGER.value: ProvenTransformationNode.EXECUTE_MIGRATION_OWNER.value,
    ProvenTransformationNode.EXECUTE_MIGRATION_OWNER.value: ProvenTransformationNode.COMPARE_DEPENDENCY_AUTHORITY.value,
    ProvenTransformationNode.COMPARE_DEPENDENCY_AUTHORITY.value: ProvenTransformationNode.FREEZE_TARGET_AUTHORITY.value,
    ProvenTransformationNode.FREEZE_TARGET_AUTHORITY.value: ProvenTransformationNode.CREATE_VALIDATION_GENERATION.value,
    ProvenTransformationNode.CREATE_VALIDATION_GENERATION.value: ProvenTransformationNode.VALIDATION_INSTALL.value,
    ProvenTransformationNode.VALIDATION_INSTALL.value: ProvenTransformationNode.VALIDATION_TREE.value,
    ProvenTransformationNode.VALIDATION_TREE.value: ProvenTransformationNode.VALIDATION_VERSION_PROOF.value,
    ProvenTransformationNode.VALIDATION_VERSION_PROOF.value: ProvenTransformationNode.VALIDATION_BUILD.value,
    ProvenTransformationNode.VALIDATION_BUILD.value: ProvenTransformationNode.VALIDATION_TEST.value,
    ProvenTransformationNode.VALIDATION_TEST.value: ProvenTransformationNode.DIAGNOSTIC_DELTA.value,
    ProvenTransformationNode.DIAGNOSTIC_DELTA.value: ProvenTransformationNode.AGGREGATE_PROVEN_VALIDATION.value,
    ProvenTransformationNode.AGGREGATE_PROVEN_VALIDATION.value: ProvenTransformationNode.PROMOTE_VALIDATED.value,
    ProvenTransformationNode.PROMOTE_VALIDATED.value: ProvenTransformationNode.PROMOTION_PENDING.value,
}

#: Proven nodes that terminate the sequential table by design: the graph
#: routes them to a gate, a block, or the sealing flow instead of a linear
#: successor.
_PROVEN_TERMINAL_NODES = frozenset(
    {
        ProvenTransformationNode.PROMOTION_PENDING.value,
        ProvenTransformationNode.DISCARD_DISCOVERY.value,
    }
)


class ProvenStageExecutionService:
    """Deterministic execution of the proven graph through existing services.

    Dependencies (V2.3 Phase 3):

    - ``stage_service``: workspace preparation, command queueing, evidence
    - ``validation``: clean-validation command groups (build/test)
    - ``lockfile_runner``: governed npm lockfile generation/reconciliation
    - ``promotion``: validated-generation promotion
    - ``sealing``: stage sealing flow
    - ``failure_router``: failure envelope normalization + owner routing
    - ``repair``: governed repair application
    - ``activation``: proven activation gate (readiness proof)
    """

    def __init__(
        self,
        *,
        scope=session_scope,
        stage_service: TransformerStageService | None = None,
        validation=None,
        lockfile_runner=None,
        promotion=None,
        sealing=None,
        failure_router=None,
        repair=None,
        activation: ProvenActivationGate | None = None,
    ) -> None:
        self._scope = scope
        self._stage = stage_service or TransformerStageService(scope=scope)
        self._validation = validation
        self._lockfiles = lockfile_runner
        self._promotion = promotion
        self._sealing = sealing
        self._failures = failure_router
        self._repairs = repair
        self._activation = activation or ProvenActivationGate()

    # -- graph-facing entry -------------------------------------------------

    def advance(self, continuation_id: str, worker_id: str, node: str) -> None:
        """Execute one proven node deterministically.

        Raises ``ProvenStageExecutionError`` for unknown nodes (the graph
        fails closed) and for proven nodes whose required service dependency
        is not wired (never a silent no-op).
        """
        handler = getattr(self, f"_node_{node}", None)
        if handler is None:
            raise ProvenStageExecutionError(
                "TRANSFORMER_PROVEN_NODE_UNSUPPORTED",
                f"proven node {node} has no registered handler",
            )
        handler(continuation_id, worker_id)

    # -- shared primitives --------------------------------------------------

    def _owned(self, session, continuation_id: str, worker_id: str) -> TransformationContinuationModel:
        continuation = session.get(TransformationContinuationModel, continuation_id)
        if continuation is None or continuation.status != "running" or continuation.worker_id != worker_id:
            raise TransformerStageError("TRANSFORMATION_CLAIM_STALE", "Worker no longer owns continuation")
        return continuation

    @staticmethod
    def _queue(continuation: TransformationContinuationModel, node: str) -> None:
        continuation.status = "queued"
        continuation.current_node = node
        continuation.worker_id = None
        continuation.lease_expires_at = None
        continuation.state_version += 1
        continuation.updated_at = datetime.now(UTC)

    @staticmethod
    def _block(
        session,
        continuation: TransformationContinuationModel,
        code: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> None:
        expected_state_version = continuation.state_version
        continuation.status = "blocked"
        continuation.last_error_code = code
        continuation.last_error_message = message
        continuation.worker_id = None
        continuation.lease_expires_at = None
        continuation.state_version += 1
        continuation.updated_at = datetime.now(UTC)
        session.flush()
        append_continuation_event(
            session,
            continuation,
            event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_BLOCKED,
            key=f"block:{expected_state_version}:{code}",
            reason=message,
            payload={
                "last_error_code": code,
                "expected_state_version": expected_state_version,
                "details": details or {},
            },
        )

    def _binding(self, session, continuation) -> StageWorkspaceBindingModel:
        bindings = session.scalars(
            select(StageWorkspaceBindingModel)
            .where(
                StageWorkspaceBindingModel.run_id == continuation.run_id,
                StageWorkspaceBindingModel.stage_id == continuation.current_stage_id,
                StageWorkspaceBindingModel.active.is_(True),
            )
            .order_by(
                StageWorkspaceBindingModel.created_at.desc(),
                StageWorkspaceBindingModel.id.desc(),
            )
        ).all()
        stage_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
        planned_aliases = {
            reference.get("working_directory_alias")
            for references in ((stage_plan.stage_plan or {}).get("commands") or {}).values()
            for reference in references
            if reference.get("working_directory_alias")
        }
        binding = next(
            (
                candidate
                for candidate in bindings
                if candidate.alias in planned_aliases
                and Path(candidate.workspace_path).is_dir()
                and StageSandboxCopier.fingerprint(Path(candidate.workspace_path))
                == candidate.workspace_fingerprint
            ),
            None,
        )
        if binding is None:
            binding = next(
                (
                    candidate
                    for candidate in bindings
                    if Path(candidate.workspace_path).is_dir()
                    and StageSandboxCopier.fingerprint(Path(candidate.workspace_path))
                    == candidate.workspace_fingerprint
                ),
                bindings[0] if bindings else None,
            )
        if binding is None:
            raise ProvenStageExecutionError(
                "PROVEN_WORKSPACE_BINDING_MISSING",
                "active stage workspace binding is missing",
            )
        return binding

    def _stage_plan(self, session, continuation) -> dict:
        plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
        if plan is None:
            raise ProvenStageExecutionError("PROVEN_STAGE_PLAN_MISSING", "stage plan is missing")
        return plan.stage_plan or {}

    def _artifact_store(self, session, continuation) -> LocalFilesystemArtifactStore:
        run = session.get(MigrationRunModel, continuation.run_id)
        if run is None or not run.artifact_root:
            raise ProvenStageExecutionError("PROVEN_ARTIFACT_ROOT_MISSING", "run artifact root is missing")
        root = Path(run.artifact_root)
        return LocalFilesystemArtifactStore(root.parent, fixed_run_root=root)

    def _record_evidence(self, session, continuation, store, relative_path: str, payload: dict, schema_version: str) -> None:
        """Write one immutable evidence artifact and bind its metadata row."""
        stored = store.write_text_artifact(
            continuation.run_id,
            relative_path,
            json.dumps(payload, sort_keys=True, indent=2),
            ArtifactType.JSON,
            stage_id=continuation.current_stage_id,
            created_by="transformer",
            created_at=datetime.now(UTC),
            input_hashes={"stage_id": continuation.current_stage_id},
            policy_version="transformer-proven-v1",
        )
        metadata_id = "metadata-" + stored.ref.artifact_id
        if session.get(ArtifactMetadataModel, metadata_id) is None:
            session.add(
                ArtifactMetadataModel(
                    id=metadata_id,
                    run_id=continuation.run_id,
                    stage_id=continuation.current_stage_id,
                    artifact_type=stored.ref.artifact_type.value,
                    relative_path=stored.ref.relative_path,
                    checksum=stored.ref.checksum,
                    schema_version=schema_version,
                    created_at=stored.ref.created_at,
                    finalized_at=stored.ref.created_at,
                    immutable=True,
                    size_bytes=len(stored.content.encode("utf-8")),
                )
            )
        return stored

    def _advance_after(self, session, continuation: TransformationContinuationModel, node: str) -> None:
        successor = _PROVEN_SUCCESSORS.get(node)
        if successor is None:
            raise ProvenStageExecutionError(
                "TRANSFORMER_PROVEN_NODE_UNSUPPORTED",
                f"proven node {node} has no successor route",
            )
        continuation.last_error_code = None
        continuation.last_error_message = None
        self._queue(continuation, successor)

    def _queue_planned_command(
        self,
        session,
        continuation,
        *,
        group: str,
        next_node: str,
        attempt_key: str,
        package: str | None = None,
        from_version: str | None = None,
        to_version: str | None = None,
        reference_override=None,
    ) -> None:
        """Queue one governed plan command and park the continuation on it."""
        attempt_key = self._scoped_attempt_key(continuation, attempt_key)
        result = self._stage._queue_group(
            session,
            continuation,
            group=group,
            next_node=next_node,
            attempt_key=attempt_key,
            reference_override=reference_override,
        )
        execution = session.get(CommandExecutionModel, result.execution_id)
        if execution is not None:
            evidence = build_command_execution_evidence(
                execution_row=execution,
                artifact_checksums=self._artifact_checksums(session, execution),
            )
            store = self._artifact_store(session, continuation)
            self._record_evidence(
                session,
                continuation,
                store,
                f"04_workflow_state/stages/{continuation.current_stage_id}/commands/{execution.id}.evidence.json",
                evidence.model_dump(mode="json"),
                "command-execution-evidence-v1",
            )

    def _queue_authority_command(
        self,
        session,
        continuation,
        *,
        command_id: str,
        purpose: str,
        group: str,
        next_node: str,
        attempt_key: str,
        package: str | None = None,
        from_version: str | None = None,
        to_version: str | None = None,
    ) -> None:
        attempt_key = self._scoped_attempt_key(continuation, attempt_key)
        CommandRegistryService().seed_defaults(session)
        stage_plan = self._stage_plan(session, continuation)
        authority = self._stage.angular_cli_authority(session, continuation, purpose=purpose)
        if purpose == "MIGRATION" and authority.requested_cli_exact != stage_plan.get("target_cli_exact"):
            raise ProvenStageExecutionError(
                "ANGULAR_CLI_TARGET_AUTHORITY_MISMATCH",
                "materialized Angular CLI does not match the approved target CLI exact version",
            )

        definition = TRANSFORMATION_COMMAND_CATALOGUE[command_id]
        bindings = {
            "governed_node_absolute": authority.node_executable_absolute,
            "angular_cli_entrypoint_absolute": authority.cli_entrypoint_absolute,
            "target_cli_entrypoint_absolute": authority.cli_entrypoint_absolute,
        }
        if command_id == "angular-update-discovery":
            cohort = stage_plan.get("target_cohort") or {}
            _require_target_cohort(
                cohort,
                source_family=str(stage_plan.get("source_family") or ""),
                target_family=str(stage_plan.get("target_family") or ""),
            )
            bindings["package"] = "@angular/core"
            for package, binding_name in (
                ("@angular/cli", "cli_package_spec"),
                ("@angular/core", "core_package_spec"),
                ("@angular/animations", "animations_package_spec"),
                ("@angular/common", "common_package_spec"),
                ("@angular/compiler", "compiler_package_spec"),
                ("@angular/compiler-cli", "compiler_cli_package_spec"),
                ("@angular/forms", "forms_package_spec"),
                ("@angular/platform-browser", "platform_browser_package_spec"),
                ("@angular/platform-browser-dynamic", "platform_browser_dynamic_package_spec"),
                ("@angular/router", "router_package_spec"),
                ("@angular-devkit/build-angular", "devkit_package_spec"),
                ("typescript", "typescript_package_spec"),
                ("rxjs", "rxjs_package_spec"),
                ("zone.js", "zone_package_spec"),
            ):
                bindings[binding_name] = f"{package}@{cohort[package]}"
            bindings["from_version"] = stage_plan["source_exact"]
            bindings["to_version"] = stage_plan["target_exact"]
        elif command_id == "angular-migrate-range-v2":
            bindings.update(
                package=package or "@angular/core",
                from_version=from_version or stage_plan["source_exact"],
                to_version=to_version or stage_plan["target_exact"],
            )
        try:
            arguments = list(definition.render_arguments(bindings))
        except ValueError as error:
            raise ProvenStageExecutionError("ANGULAR_CLI_COMMAND_BINDING_INVALID", str(error)) from error
        reference = {
            "command_id": definition.command_id,
            "template_id": definition.template_id,
            "template_version": 9 if command_id == "angular-update-discovery" else 1,
            "parameter_bindings": bindings,
            "executable": authority.node_executable_absolute,
            "arguments": arguments,
            "working_directory_alias": f"STAGE_WORKSPACE_{continuation.current_stage_id.upper().replace('-', '_')}",
            "timeout_seconds": definition.timeout_seconds,
            "network_profile": definition.network_profile,
            "cancellation_policy": "terminate_process_tree",
            "runtime_profile_checksum": self._stage.runtime_binding(session, continuation)["checksum"],
        }
        store = self._artifact_store(session, continuation)
        self._record_evidence(
            session,
            continuation,
            store,
            f"04_workflow_state/stages/{continuation.current_stage_id}/angular-cli/{purpose.lower()}-authority.json",
            authority.model_dump(mode="json"),
            "angular-cli-toolchain-authority-v1",
        )
        result = self._stage._queue_group(
            session,
            continuation,
            group=group,
            next_node=next_node,
            attempt_key=attempt_key,
            reference_override=reference,
        )
        execution = session.get(CommandExecutionModel, result.execution_id)
        if execution is not None:
            evidence = build_command_execution_evidence(
                execution_row=execution,
                artifact_checksums=self._artifact_checksums(session, execution),
            )
            self._record_evidence(
                session,
                continuation,
                store,
                f"04_workflow_state/stages/{continuation.current_stage_id}/commands/{execution.id}.evidence.json",
                evidence.model_dump(mode="json"),
                "command-execution-evidence-v1",
            )

    def _queue_authority_or_block(self, session, continuation, **kwargs) -> None:
        try:
            self._queue_authority_command(session, continuation, **kwargs)
        except (TransformerStageError, ProvenStageExecutionError) as error:
            self._block(
                session,
                continuation,
                getattr(error, "code", "ANGULAR_CLI_AUTHORITY_FAILED"),
                str(error),
                getattr(error, "details", None),
            )

    def _artifact_checksums(self, session, execution) -> dict[str, str]:
        """Resolve committed artifact checksums for one execution row."""
        checksums: dict[str, str] = {}
        for artifact_id in (
            execution.stdout_artifact_id,
            execution.stderr_artifact_id,
            execution.command_log_artifact_id,
            execution.result_artifact_id,
            execution.manifest_artifact_id,
        ):
            if not artifact_id:
                continue
            metadata = session.get(ArtifactMetadataModel, "metadata-" + artifact_id)
            if metadata is not None:
                checksums[artifact_id] = metadata.checksum
        return checksums

    def _latest_terminal_execution(self, session, continuation, group: str) -> CommandExecutionModel | None:
        step = session.scalar(
            select(StageStepModel).where(
                StageStepModel.stage_id == continuation.current_stage_id,
                StageStepModel.name == f"{group}-0",
            )
        )
        if step is None or not step.execution_id:
            return None
        execution = session.get(CommandExecutionModel, step.execution_id)
        if execution is None or execution.plan_id != continuation.plan_id:
            return None
        return execution

    @staticmethod
    def _scoped_attempt_key(continuation, attempt_key: str) -> str:
        """Bind generated command identities to their active authority."""
        plan_id = getattr(continuation, "plan_id", None) or ""
        stage_plan_id = getattr(continuation, "stage_plan_id", None) or ""
        if not plan_id and not stage_plan_id:
            return attempt_key
        digest = hashlib.sha256(
            f"{plan_id}:{stage_plan_id}:{attempt_key}".encode("utf-8")
        ).hexdigest()[:32]
        return f"plan-{digest}"

    # -- Phase 1: source baseline -------------------------------------------

    def _node_select_run_mode(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            plan = self._stage_plan(session, continuation)
            run_mode = plan.get("run_mode", "PRODUCTION")
            if run_mode not in {"PRODUCTION", "QUALIFICATION"}:
                self._block(session, continuation, "PROVEN_PLAN_MODE_UNSUPPORTED", f"unsupported run mode: {run_mode}")
                return
            if run_mode == "QUALIFICATION" and not plan.get("qualification_authorization_checksum"):
                self._block(
                    session,
                    continuation,
                    "TRANSFORMER_QUALIFICATION_AUTHORIZATION_REQUIRED",
                    "qualification plans require an explicit authorization checksum",
                )
                return
            self._advance_after(session, continuation, ProvenTransformationNode.SELECT_RUN_MODE.value)

    def _node_prepare_stage_layout(self, continuation_id: str, worker_id: str) -> None:
        # Real workspace preparation (stage service owns the durable layout
        # and pre_bootstrap checkpoint); the legacy successor node is
        # overridden to the proven entry point after preparation commits.
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            stage = session.get(MigrationStageModel, continuation.current_stage_id)
            binding = self._binding(session, continuation)
            workspace = Path(binding.workspace_path)
            if (
                stage is not None
                and stage.status == "prepared"
                and workspace.is_dir()
                and StageSandboxCopier.fingerprint(workspace) == binding.workspace_fingerprint
            ):
                self._advance_after(session, continuation, ProvenTransformationNode.PREPARE_STAGE_LAYOUT.value)
                return
        self._stage.prepare(continuation_id, worker_id)
        with self._scope() as session:
            # prepare() released the claim and queued the legacy successor;
            # re-own the row without the running-status assertion.
            continuation = session.get(TransformationContinuationModel, continuation_id)
            if continuation is None:
                raise ProvenStageExecutionError("PROVEN_CONTINUATION_MISSING", "continuation is missing after preparation")
            self._advance_after(session, continuation, ProvenTransformationNode.PREPARE_STAGE_LAYOUT.value)

    def _node_create_source_baseline(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            if not self._activation.verify().passed:
                self._block(
                    session,
                    continuation,
                    "TRANSFORMER_PROVEN_ACTIVATION_BLOCKED",
                    "proven execution layer is not fully wired; activation gate failed",
                )
                return
            self._advance_after(session, continuation, ProvenTransformationNode.CREATE_SOURCE_BASELINE.value)

    def _node_construct_dependency_intent(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            binding = self._binding(session, continuation)
            workspace = Path(binding.workspace_path)
            package_json = workspace / "package.json"
            if not package_json.is_file():
                self._block(session, continuation, "PROVEN_MANIFEST_MISSING", "package.json is missing from the workspace")
                return
            intent = _dependency_intent_from_workspace(workspace)
            store = self._artifact_store(session, continuation)
            self._record_evidence(
                session,
                continuation,
                store,
                f"04_workflow_state/stages/{continuation.current_stage_id}/proven/source-dependency-intent.json",
                intent,
                "dependency-intent-v1",
            )
            self._advance_after(session, continuation, ProvenTransformationNode.CONSTRUCT_DEPENDENCY_INTENT.value)

    def _node_bind_npm_lock_authority_policy(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            binding = self._binding(session, continuation)
            workspace = Path(binding.workspace_path)
            selected = _select_lock_authority(workspace)
            if selected is None:
                self._block(session, continuation, "PROVEN_LOCK_AUTHORITY_MISSING", "no package-lock/npm-shrinkwrap authority found")
                return
            store = self._artifact_store(session, continuation)
            self._record_evidence(
                session,
                continuation,
                store,
                f"04_workflow_state/stages/{continuation.current_stage_id}/proven/source-lock-authority.json",
                {"filename": selected[0], "kind": selected[1], "raw_sha256": selected[2]},
                "lockfile-authority-v1",
            )
            self._advance_after(session, continuation, ProvenTransformationNode.BIND_NPM_LOCK_AUTHORITY_POLICY.value)

    def _node_select_source_lock_authority(self, continuation_id: str, worker_id: str) -> None:
        self._advance_recorded(continuation_id, worker_id, ProvenTransformationNode.SELECT_SOURCE_LOCK_AUTHORITY.value)

    def _node_read_source_resolved_lock(self, continuation_id: str, worker_id: str) -> None:
        self._advance_recorded(continuation_id, worker_id, ProvenTransformationNode.READ_SOURCE_RESOLVED_LOCK.value)

    def _node_prove_source_manifest_vs_resolution(self, continuation_id: str, worker_id: str) -> None:
        self._advance_recorded(continuation_id, worker_id, ProvenTransformationNode.PROVE_SOURCE_MANIFEST_VS_RESOLUTION.value)

    def _advance_recorded(self, continuation_id: str, worker_id: str, node: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            self._advance_after(session, continuation, node)

    def _node_source_install_same_authority(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            existing = self._latest_terminal_execution(session, continuation, "bootstrap_install")
            binding = self._binding(session, continuation)
            cli_package = Path(binding.workspace_path) / "node_modules" / "@angular" / "cli" / "package.json"
            if existing is not None and existing.status == "succeeded" and cli_package.is_file():
                self._advance_after(session, continuation, ProvenTransformationNode.SOURCE_INSTALL_SAME_AUTHORITY.value)
                return
            self._queue_planned_command(
                session,
                continuation,
                group="bootstrap_install",
                next_node=ProvenTransformationNode.SOURCE_TREE.value,
                attempt_key=(
                    "source-install"
                    if existing is None
                    else f"source-install-recovery:{continuation.state_version}"
                ),
            )

    def _node_source_tree(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            execution = self._latest_terminal_execution(session, continuation, "bootstrap_install")
            if execution is None or execution.status != "succeeded":
                if execution is not None and execution.status in {"interrupted", "failed"}:
                    self._queue(continuation, ProvenTransformationNode.SOURCE_INSTALL_SAME_AUTHORITY.value)
                    continuation.last_error_code = "PROVEN_SOURCE_INSTALL_RETRY_QUEUED"
                    continuation.last_error_message = "source install did not reach terminal success; requeueing governed source install"
                    return
                self._block(session, continuation, "PROVEN_SOURCE_INSTALL_NOT_VERIFIED", "source install lacks terminal success evidence")
                return
            existing = self._latest_terminal_execution(session, continuation, "dependency_tree")
            if existing is not None and existing.status == "succeeded":
                self._advance_after(session, continuation, ProvenTransformationNode.SOURCE_TREE.value)
                return
            self._queue_planned_command(
                session,
                continuation,
                group="dependency_tree",
                next_node=ProvenTransformationNode.SOURCE_VERSION_PROOF.value,
                attempt_key="source-tree",
            )

    def _node_source_version_proof(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            execution = self._latest_terminal_execution(session, continuation, "dependency_tree")
            if execution is None or execution.status != "succeeded":
                self._block(session, continuation, "PROVEN_SOURCE_TREE_NOT_VERIFIED", "source tree lacks terminal success evidence")
                return
            existing = self._latest_terminal_execution(session, continuation, "target_version_check")
            if existing is not None and existing.status == "succeeded":
                self._advance_after(session, continuation, ProvenTransformationNode.SOURCE_VERSION_PROOF.value)
                return
            self._queue_planned_command(
                session,
                continuation,
                group="target_version_check",
                next_node=ProvenTransformationNode.SOURCE_BUILD.value,
                attempt_key="source-version-proof",
            )

    def _node_source_build(self, continuation_id: str, worker_id: str) -> None:
        self._validate_group(
            continuation_id,
            worker_id,
            group="builds",
            node=ProvenTransformationNode.SOURCE_BUILD.value,
            next_node=ProvenTransformationNode.SOURCE_TEST.value,
            step_group="target_version_check",
        )

    def _node_source_test(self, continuation_id: str, worker_id: str) -> None:
        self._validate_group(
            continuation_id,
            worker_id,
            group="tests",
            node=ProvenTransformationNode.SOURCE_TEST.value,
            next_node=ProvenTransformationNode.SOURCE_DIAGNOSTIC_CAPTURE.value,
            step_group="builds",
        )

    @staticmethod
    def _validation_attempt_key(continuation, node: str) -> str:
        if continuation.last_error_code == "FAILURE_ROUTE_ENVIRONMENT_TRANSIENT":
            attempt_key = f"environment-retry:{continuation.attempt}:{node}"
        elif continuation.last_error_code == "VALIDATION_COMMAND_AUTH_RETRY_QUEUED":
            attempt_key = f"workspace-binding-retry:{continuation.state_version}:{node}"
        elif continuation.last_error_code == "VALIDATION_COMMAND_IDEMPOTENCY_RETRY_QUEUED":
            attempt_key = f"stage-validation-retry:{continuation.state_version}:{node}"
        else:
            attempt_key = f"proven:{node}"
        return ProvenStageExecutionService._scoped_attempt_key(continuation, attempt_key)

    def _validate_group(self, continuation_id, worker_id, *, group, node, next_node, step_group) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            if self._validation is None:
                self._block(session, continuation, "PROVEN_VALIDATION_RUNNER_MISSING", "validation runner is not wired")
                return
            prior = self._latest_terminal_execution(session, continuation, step_group)
            if prior is None or prior.status != "succeeded":
                self._block(session, continuation, "PROVEN_PRIOR_STEP_NOT_VERIFIED", f"{step_group} lacks terminal success evidence")
                return
            try:
                self._validation.advance_group(
                    session,
                    continuation,
                    group,
                    next_node=next_node,
                    attempt_key=self._validation_attempt_key(continuation, node),
                )
            except Exception as error:
                # ValidationRunner already queues ``classify_failure`` for
                # failed command evidence; structural runner errors also route
                # through the governed failure classification instead of
                # inventing a repair path here.
                from app.services.validation_runner import ValidationRunnerError

                code = error.code if isinstance(error, ValidationRunnerError) else "PROVEN_VALIDATION_ADVANCE_FAILED"
                expected_state_version = continuation.state_version
                continuation.status = "queued"
                continuation.current_node = "classify_failure"
                continuation.last_error_code = code
                continuation.last_error_message = str(error)
                continuation.state_version += 1
                continuation.updated_at = datetime.now(UTC)
                session.flush()
                append_continuation_event(
                    session,
                    continuation,
                    event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_FAILED,
                    key=f"failed:{expected_state_version}:{code}",
                    reason="proven validation advance failed; failure classification queued",
                    payload={"last_error_code": code, "expected_state_version": expected_state_version},
                )

    def _node_source_diagnostic_capture(self, continuation_id: str, worker_id: str) -> None:
        self._advance_recorded(continuation_id, worker_id, ProvenTransformationNode.SOURCE_DIAGNOSTIC_CAPTURE.value)

    def _node_freeze_source_baseline(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            binding = self._binding(session, continuation)
            workspace = Path(binding.workspace_path)
            package_json = workspace / "package.json"
            store = self._artifact_store(session, continuation)
            payload = {
                "run_id": continuation.run_id,
                "stage_id": continuation.current_stage_id,
                "package_json_sha256": _file_sha256(package_json) if package_json.is_file() else None,
                "workspace_fingerprint": binding.workspace_fingerprint,
                "status": "FROZEN",
            }
            self._record_evidence(
                session,
                continuation,
                store,
                f"04_workflow_state/stages/{continuation.current_stage_id}/proven/source-baseline.json",
                payload,
                "source-baseline-evidence-v1",
            )
            self._advance_after(session, continuation, ProvenTransformationNode.FREEZE_SOURCE_BASELINE.value)

    # -- Phase 2: target discovery ------------------------------------------

    def _node_create_discovery_generation(self, continuation_id: str, worker_id: str) -> None:
        self._advance_recorded(continuation_id, worker_id, ProvenTransformationNode.CREATE_DISCOVERY_GENERATION.value)

    def _node_prepare_discovery_toolchain(self, continuation_id: str, worker_id: str) -> None:
        self._advance_recorded(continuation_id, worker_id, ProvenTransformationNode.PREPARE_DISCOVERY_TOOLCHAIN.value)

    def _node_prove_discovery_cli_authority(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            binding = self._binding(session, continuation)
            cli_package = Path(binding.workspace_path) / "node_modules" / "@angular" / "cli" / "package.json"
            if not cli_package.is_file():
                self._queue(continuation, ProvenTransformationNode.SOURCE_INSTALL_SAME_AUTHORITY.value)
                continuation.last_error_code = "PROVEN_SOURCE_INSTALL_PHYSICAL_MISSING"
                continuation.last_error_message = "discovery requires a physical installed Angular CLI; source install was requeued"
                return
            self._queue_authority_or_block(
                session,
                continuation,
                command_id="angular-cli-authority-version",
                purpose="DISCOVERY",
                group="cli_authority_version",
                next_node=ProvenTransformationNode.RUN_DISCOVERY.value,
                attempt_key=f"discovery-cli-version:{continuation.state_version}",
            )

    def _node_run_discovery(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            stage_plan = self._stage_plan(session, continuation)
            target_exact = stage_plan.get("target_exact")
            if not target_exact:
                self._block(session, continuation, "PROVEN_TARGET_EXACT_MISSING", "stage plan has no exact target version")
                return
            self._queue_authority_or_block(
                session,
                continuation,
                command_id="angular-update-discovery",
                purpose="DISCOVERY",
                group="discovery",
                next_node=ProvenTransformationNode.ASSESS_DISCOVERY.value,
                attempt_key=f"discovery:{continuation.state_version}",
            )

    def _node_assess_discovery(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            execution = self._latest_terminal_execution(session, continuation, "discovery")
            if execution is None:
                self._block(session, continuation, "PROVEN_DISCOVERY_EVIDENCE_MISSING", "discovery execution evidence is missing")
                return
            if execution.status != "succeeded":
                failure_text = (execution.failure_message or "").lower()
                network_transient = any(
                    marker in failure_text
                    for marker in ("socket timeout", "etimedout", "eai_again", "network timeout")
                )
                attempts = session.scalars(
                    select(CommandExecutionModel).where(
                        CommandExecutionModel.run_id == continuation.run_id,
                        CommandExecutionModel.stage_id == continuation.current_stage_id,
                        CommandExecutionModel.command_id == "angular-update-discovery",
                        CommandExecutionModel.template_id == "tpl-angular-update-discovery-v9",
                    )
                ).all()
                max_attempts = 3 if network_transient or attempts else 2
                if len(attempts) >= max_attempts:
                    envelope = self._failure_envelope_from_execution(
                        session, continuation, execution, FailureCategory.DISCOVERY, "discovery"
                    )
                    self._block(
                        session,
                        continuation,
                        execution.failure_code or "PROVEN_DISCOVERY_FAILED",
                        envelope.message,
                    )
                    return
                run = session.get(MigrationRunModel, continuation.run_id)
                binding = self._binding(session, continuation)
                aliases = dict(run.workspace_aliases or {}) if run is not None else {}
                baseline = aliases.get("BASELINE_SANDBOX")
                stage_root = aliases.get("STAGE_SANDBOX")
                expected = aliases.get("BASELINE_SANDBOX_FINGERPRINT") or binding.workspace_fingerprint
                if not baseline or not stage_root:
                    self._block(session, continuation, "PROVEN_DISCOVERY_RECONSTRUCTION_FAILED", "immutable sealed predecessor is unavailable for discovery recovery")
                    return
                try:
                    restored = TransformerStageService.reconstruct_workspace(
                        baseline,
                        binding.workspace_path,
                        stage_root,
                        expected,
                    )
                except TransformerStageError as error:
                    self._block(session, continuation, error.code, error.message)
                    return
                binding.workspace_fingerprint = restored
                binding.last_verified_fingerprint = restored
                binding.last_verified_at = datetime.now(UTC)
                store = self._artifact_store(session, continuation)
                self._record_evidence(
                    session,
                    continuation,
                    store,
                    f"04_workflow_state/stages/{continuation.current_stage_id}/proven/discovery-recovery-{execution.id}.json",
                    {
                        "execution_id": execution.id,
                        "source": baseline,
                        "restored_workspace": binding.workspace_path,
                        "restored_fingerprint": restored,
                        "reason": "discovery authority is disposable and failed after mutating the candidate manifest",
                    },
                    "discovery-workspace-recovery-v1",
                )
                self._queue(continuation, ProvenTransformationNode.SOURCE_INSTALL_SAME_AUTHORITY.value)
                continuation.last_error_code = "PROVEN_DISCOVERY_WORKSPACE_RESTORED"
                continuation.last_error_message = "discovery workspace was restored from the sealed predecessor; source install is being revalidated"
                return
            self._advance_after(session, continuation, ProvenTransformationNode.ASSESS_DISCOVERY.value)

    def _node_persist_target_intent(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            stage_plan = self._stage_plan(session, continuation)
            binding = self._binding(session, continuation)
            package_json = Path(binding.workspace_path) / "package.json"
            store = self._artifact_store(session, continuation)
            payload = {
                "run_id": continuation.run_id,
                "stage_id": continuation.current_stage_id,
                "target_cohort": stage_plan.get("target_cohort") or {},
                "target_exact": stage_plan.get("target_exact"),
                "target_cli_exact": stage_plan.get("target_cli_exact"),
                "source_package_json_sha256": _file_sha256(package_json) if package_json.is_file() else None,
                "discovery_complete": True,
            }
            self._record_evidence(
                session,
                continuation,
                store,
                f"04_workflow_state/stages/{continuation.current_stage_id}/proven/target-intent.json",
                payload,
                "target-intent-v1",
            )
            self._advance_after(session, continuation, ProvenTransformationNode.PERSIST_TARGET_INTENT.value)

    def _node_discard_discovery(self, continuation_id: str, worker_id: str) -> None:
        """Discovery was discarded: the disposable result is never promoted.

        Terminal leaf — the graph blocks with explicit evidence so the
        operator (or repair governance) decides the next step.
        """
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            store = self._artifact_store(session, continuation)
            self._record_evidence(
                session,
                continuation,
                store,
                f"04_workflow_state/stages/{continuation.current_stage_id}/proven/discovery-discarded.json",
                {"run_id": continuation.run_id, "stage_id": continuation.current_stage_id, "status": "DISCARDED"},
                "discovery-discard-v1",
            )
            self._block(
                session,
                continuation,
                "PROVEN_DISCOVERY_DISCARDED",
                "target discovery was discarded; no TargetIntent was persisted",
            )

    # -- Phase 3: lock resolution -------------------------------------------

    def _node_create_authoritative_target(self, continuation_id: str, worker_id: str) -> None:
        self._advance_recorded(continuation_id, worker_id, ProvenTransformationNode.CREATE_AUTHORITATIVE_TARGET.value)

    def _node_apply_target_intent(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            stage_plan = self._stage_plan(session, continuation)
            binding = self._binding(session, continuation)
            workspace = Path(binding.workspace_path)
            package_json = workspace / "package.json"
            if not package_json.is_file():
                self._block(session, continuation, "PROVEN_MANIFEST_MISSING", "package.json is missing from the workspace")
                return
            cohort = stage_plan.get("target_cohort") or {}
            try:
                _apply_target_cohort(
                    workspace,
                    cohort,
                    source_family=stage_plan.get("source_family"),
                    target_family=stage_plan.get("target_family"),
                )
            except ProvenStageExecutionError as error:
                self._block(session, continuation, error.code, error.message, error.details)
                return
            self._advance_after(session, continuation, ProvenTransformationNode.APPLY_TARGET_INTENT.value)

    def _node_dependency_plan(self, continuation_id: str, worker_id: str) -> None:
        self._advance_recorded(continuation_id, worker_id, ProvenTransformationNode.DEPENDENCY_PLAN.value)

    def _node_select_target_lock_authority(self, continuation_id: str, worker_id: str) -> None:
        self._advance_recorded(continuation_id, worker_id, ProvenTransformationNode.SELECT_TARGET_LOCK_AUTHORITY.value)

    def _node_lock_resolution(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            try:
                run = session.get(MigrationRunModel, continuation.run_id)
                _clear_target_node_modules(
                    self._binding(session, continuation),
                    run.source_path if run is not None else None,
                    self._stage_plan(session, continuation).get("target_cohort") or {},
                    source_family=self._stage_plan(session, continuation).get("source_family"),
                    target_family=self._stage_plan(session, continuation).get("target_family"),
                )
                lock_reference = dict(
                    (self._stage_plan(session, continuation).get("commands") or {})
                    .get("lockfile_generation", [{}])[0]
                )
                self._queue_planned_command(
                    session,
                    continuation,
                    group="lockfile_generation",
                    attempt_key=f"target-lockfile-generation:{continuation.state_version}",
                    next_node=ProvenTransformationNode.CREATE_MATERIALIZATION.value,
                    reference_override=lock_reference,
                )
            except Exception as error:
                self._block(session, continuation, "PROVEN_LOCK_RESOLUTION_FAILED", str(error))

    # -- Phase 4: materialization -------------------------------------------

    def _node_create_materialization(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            execution = self._latest_terminal_execution(session, continuation, "lockfile_generation")
            if execution is None or execution.status != "succeeded":
                if continuation.last_error_code != "PROVEN_LOCK_RESOLUTION_RETRY_QUEUED":
                    self._queue(continuation, ProvenTransformationNode.LOCK_RESOLUTION.value)
                    continuation.last_error_code = "PROVEN_LOCK_RESOLUTION_RETRY_QUEUED"
                    continuation.last_error_message = "target lock resolution is being retried from normalized source authority"
                    return
                self._block(
                    session,
                    continuation,
                    "PROVEN_LOCK_RESOLUTION_FAILED",
                    "target materialization lacks terminal lockfile-generation success evidence after normalized retry",
                )
                return
            self._advance_after(session, continuation, ProvenTransformationNode.CREATE_MATERIALIZATION.value)

    def _node_target_install_same_authority(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            run = session.get(MigrationRunModel, continuation.run_id)
            stage_plan = self._stage_plan(session, continuation)
            _clear_target_node_modules(
                self._binding(session, continuation),
                run.source_path if run is not None else None,
                stage_plan.get("target_cohort") or {},
                source_family=stage_plan.get("source_family"),
                target_family=stage_plan.get("target_family"),
            )
            reference = dict(
                (stage_plan.get("commands") or {})
                .get("final_install", [{}])[0]
            )
            self._queue_planned_command(
                session,
                continuation,
                group="final_install",
                next_node=ProvenTransformationNode.TARGET_TREE.value,
                attempt_key=f"target-install:{continuation.state_version}",
                reference_override=reference,
            )

    def _node_target_tree(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            execution = self._latest_terminal_execution(session, continuation, "final_install")
            if execution is None or execution.status != "succeeded":
                lockfile = self._latest_terminal_execution(session, continuation, "lockfile_generation")
                failure_reason = execution.failure_message if execution is not None else ""
                lock_sync_failure = "package.json and package-lock" in (failure_reason or "")
                lock_sync_failures = len(
                    session.scalars(
                        select(CommandExecutionModel).where(
                            CommandExecutionModel.run_id == continuation.run_id,
                            CommandExecutionModel.stage_id == continuation.current_stage_id,
                            CommandExecutionModel.plan_id == continuation.plan_id,
                            CommandExecutionModel.command_id == "npm-ci-final",
                            CommandExecutionModel.failure_message.contains("package.json and package-lock"),
                        )
                    ).all()
                )
                v2_lock_attempts = len(
                    session.scalars(
                        select(CommandExecutionModel).where(
                            CommandExecutionModel.run_id == continuation.run_id,
                            CommandExecutionModel.stage_id == continuation.current_stage_id,
                            CommandExecutionModel.plan_id == continuation.plan_id,
                            CommandExecutionModel.command_id == "npm-lockfile-generate",
                            CommandExecutionModel.template_id == "tpl-npm-lockfile-generate-v2",
                        )
                    ).all()
                )
                if (
                    lockfile is not None
                    and lockfile.status != "succeeded"
                    or lock_sync_failure
                    and (lock_sync_failures < 3 or v2_lock_attempts == 0)
                    and continuation.last_error_code != "PROVEN_LOCK_RESOLUTION_RETRY_QUEUED"
                ):
                    self._queue(continuation, ProvenTransformationNode.LOCK_RESOLUTION.value)
                    continuation.last_error_code = "PROVEN_LOCK_RESOLUTION_RETRY_QUEUED"
                    continuation.last_error_message = "target install was not attempted against a resolved target lockfile"
                    return
                self._block(session, continuation, "PROVEN_TARGET_INSTALL_NOT_VERIFIED", "target install lacks terminal success evidence")
                return
            self._advance_after(session, continuation, ProvenTransformationNode.TARGET_TREE.value)

    def _node_target_version_proof(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            self._queue_planned_command(
                session,
                continuation,
                group="target_version_check",
                next_node=ProvenTransformationNode.INSPECT_MIGRATION_METADATA.value,
                attempt_key="target-version-proof",
            )

    # -- Phase 5: migration execution ---------------------------------------

    def _node_inspect_migration_metadata(self, continuation_id: str, worker_id: str) -> None:
        self._advance_recorded(continuation_id, worker_id, ProvenTransformationNode.INSPECT_MIGRATION_METADATA.value)

    def _node_build_migration_ledger(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            binding = self._binding(session, continuation)
            workspace = Path(binding.workspace_path)
            store = self._artifact_store(session, continuation)
            payload = {
                "run_id": continuation.run_id,
                "stage_id": continuation.current_stage_id,
                "owners": _discover_migration_owners(workspace),
                "status": "READY",
            }
            self._record_evidence(
                session,
                continuation,
                store,
                f"04_workflow_state/stages/{continuation.current_stage_id}/proven/migration-ledger.json",
                payload,
                "migration-ledger-v1",
            )
            self._advance_after(session, continuation, ProvenTransformationNode.BUILD_MIGRATION_LEDGER.value)

    def _node_execute_migration_owner(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            stage_plan = self._stage_plan(session, continuation)
            binding = self._binding(session, continuation)
            run = session.get(MigrationRunModel, continuation.run_id)
            aliases = dict(run.workspace_aliases or {}) if run is not None else {}
            baseline = aliases.get("BASELINE_SANDBOX")
            if not baseline:
                self._block(session, continuation, "PROVEN_MIGRATION_OWNER_EVIDENCE_MISSING", "sealed predecessor is unavailable for migration-owner discovery")
                return
            try:
                owners = PackageMigrationService().discover(Path(baseline), Path(binding.workspace_path))
            except PackageMigrationError as error:
                self._block(session, continuation, error.code, error.message)
                return
            if not owners:
                self._advance_after(session, continuation, ProvenTransformationNode.COMPARE_DEPENDENCY_AUTHORITY.value)
                return
            executions = session.scalars(
                select(CommandExecutionModel).where(
                    CommandExecutionModel.run_id == continuation.run_id,
                    CommandExecutionModel.stage_id == continuation.current_stage_id,
                    CommandExecutionModel.plan_id == continuation.plan_id,
                    CommandExecutionModel.command_id == "angular-migrate-range-v2",
                    CommandExecutionModel.status == "succeeded",
                )
            ).all()
            def completed(owner) -> bool:
                expected = ["update", owner.package, "--migrate-only", "--from", owner.from_version, "--to", owner.to_version]
                return any(list(execution.arguments or [])[1:] == expected for execution in executions)
            owner = next((candidate for candidate in owners if not completed(candidate)), None)
            if owner is None:
                self._advance_after(session, continuation, ProvenTransformationNode.COMPARE_DEPENDENCY_AUTHORITY.value)
                return
            remaining = [candidate for candidate in owners if candidate is not owner and not completed(candidate)]
            self._queue_authority_or_block(
                session,
                continuation,
                command_id="angular-migrate-range-v2",
                purpose="MIGRATION",
                group="migrate_packages",
                next_node=(
                    ProvenTransformationNode.EXECUTE_MIGRATION_OWNER.value
                    if remaining
                    else ProvenTransformationNode.COMPARE_DEPENDENCY_AUTHORITY.value
                ),
                attempt_key=f"migration-owner:{owner.package}:{owner.from_version}->{owner.to_version}",
                package=owner.package,
                from_version=owner.from_version,
                to_version=owner.to_version,
            )

    def _node_compare_dependency_authority(self, continuation_id: str, worker_id: str) -> None:
        self._advance_recorded(continuation_id, worker_id, ProvenTransformationNode.COMPARE_DEPENDENCY_AUTHORITY.value)

    def _node_freeze_target_authority(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            binding = self._binding(session, continuation)
            workspace = Path(binding.workspace_path)
            store = self._artifact_store(session, continuation)
            package_json = workspace / "package.json"
            payload = {
                "run_id": continuation.run_id,
                "stage_id": continuation.current_stage_id,
                "package_json_sha256": _file_sha256(package_json) if package_json.is_file() else None,
                "workspace_fingerprint": binding.workspace_fingerprint,
                "status": "FROZEN",
            }
            self._record_evidence(
                session,
                continuation,
                store,
                f"04_workflow_state/stages/{continuation.current_stage_id}/proven/target-authority-freeze.json",
                payload,
                "dependency-authority-freeze-v1",
            )
            self._advance_after(session, continuation, ProvenTransformationNode.FREEZE_TARGET_AUTHORITY.value)

    # -- Phase 6: validation -------------------------------------------------

    def _node_create_validation_generation(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            for name in (
                "final_install-0",
                "target_version_check-0",
                "builds-0",
                "tests-0",
                "lint-0",
            ):
                step = session.scalar(
                    select(StageStepModel).where(
                        StageStepModel.stage_id == continuation.current_stage_id,
                        StageStepModel.name == name,
                    )
                )
                if step is not None:
                    step.status = "PENDING"
                    step.execution_id = None
                    step.started_at = None
                    step.completed_at = None
                    step.output_checksum = None
                    step.workspace_fingerprint = None
                    step.artifact_ids = []
                    step.updated_at = datetime.now(UTC)
        self._advance_recorded(continuation_id, worker_id, ProvenTransformationNode.CREATE_VALIDATION_GENERATION.value)

    def _node_validation_install(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            self._queue_planned_command(
                session,
                continuation,
                group="final_install",
                next_node=ProvenTransformationNode.VALIDATION_TREE.value,
                attempt_key="validation-install",
            )

    def _node_validation_tree(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            execution = self._latest_terminal_execution(session, continuation, "final_install")
            if execution is None or execution.status != "succeeded":
                self._block(session, continuation, "PROVEN_VALIDATION_INSTALL_NOT_VERIFIED", "validation install lacks terminal success evidence")
                return
            step = session.scalar(
                select(StageStepModel).where(
                    StageStepModel.stage_id == continuation.current_stage_id,
                    StageStepModel.name == "final_install-0",
                )
            )
            binding = self._binding(session, continuation)
            if step is None:
                self._block(session, continuation, "PROVEN_VALIDATION_INSTALL_STEP_MISSING", "validation install step is missing")
                return
            if step.status != "PASSED":
                observed = StageSandboxCopier.fingerprint(Path(binding.workspace_path))
                expected = (execution.start_fingerprint or {}).get("source_config")
                if expected and observed != expected:
                    self._block(session, continuation, "PROVEN_VALIDATION_WORKSPACE_MUTATED", "validation install changed governed source files")
                    return
                step.status = "PASSED"
                step.completed_at = datetime.now(UTC)
                step.workspace_fingerprint = observed
                step.output_checksum = execution.runtime_checksum
                step.artifact_ids = list(execution.artifact_ids or [])
                step.updated_at = datetime.now(UTC)
                binding.workspace_fingerprint = observed
                binding.last_verified_fingerprint = observed
                binding.last_verified_at = datetime.now(UTC)
            self._advance_after(session, continuation, ProvenTransformationNode.VALIDATION_TREE.value)

    def _node_validation_version_proof(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            self._queue_planned_command(
                session,
                continuation,
                group="target_version_check",
                next_node=ProvenTransformationNode.VALIDATION_BUILD.value,
                attempt_key="validation-version-proof",
            )

    def _node_validation_build(self, continuation_id: str, worker_id: str) -> None:
        self._validate_group(
            continuation_id,
            worker_id,
            group="builds",
            node=ProvenTransformationNode.VALIDATION_BUILD.value,
            next_node=ProvenTransformationNode.VALIDATION_TEST.value,
            step_group="target_version_check",
        )

    def _node_validation_test(self, continuation_id: str, worker_id: str) -> None:
        self._validate_group(
            continuation_id,
            worker_id,
            group="tests",
            node=ProvenTransformationNode.VALIDATION_TEST.value,
            next_node=ProvenTransformationNode.DIAGNOSTIC_DELTA.value,
            step_group="builds",
        )

    def _node_diagnostic_delta(self, continuation_id: str, worker_id: str) -> None:
        self._advance_recorded(continuation_id, worker_id, ProvenTransformationNode.DIAGNOSTIC_DELTA.value)

    def _node_aggregate_proven_validation(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            binding = self._binding(session, continuation)
            plan = self._stage_plan(session, continuation)
            required_checks = (plan.get("validation_policy") or {}).get("required_checks") or ("build", "test")
            group_by_check = {"build": "builds", "test": "tests", "lint": "lint"}
            required_groups = ["final_install"]
            for check in required_checks:
                group = group_by_check.get(check)
                if group is None:
                    self._block(session, continuation, "PROVEN_VALIDATION_CHECK_UNSUPPORTED", f"unsupported required validation check: {check}")
                    return
                if group not in required_groups:
                    required_groups.append(group)
            steps = []
            for group in required_groups:
                references = (plan.get("commands") or {}).get(group) or []
                if not references:
                    self._block(session, continuation, "PROVEN_VALIDATION_TARGET_MISSING", f"required validation target {group} is missing")
                    return
                for index in range(len(references)):
                    step = session.scalar(
                        select(StageStepModel).where(
                            StageStepModel.stage_id == continuation.current_stage_id,
                            StageStepModel.name == f"{group}-{index}",
                        )
                    )
                    if step is None:
                        self._block(session, continuation, "PROVEN_VALIDATION_STEP_MISSING", f"required validation step {group}-{index} is missing")
                        return
                    execution = session.get(CommandExecutionModel, step.execution_id) if step.execution_id else None
                    if (
                        group == "final_install"
                        and step.status != "PASSED"
                        and execution is not None
                        and execution.status == "succeeded"
                        and execution.command_log_artifact_id
                        and execution.result_artifact_id
                    ):
                        observed = StageSandboxCopier.fingerprint(Path(binding.workspace_path))
                        expected = (execution.start_fingerprint or {}).get("source_config")
                        if expected and observed != expected:
                            self._block(session, continuation, "PROVEN_VALIDATION_WORKSPACE_MUTATED", "validation install changed governed source files")
                            return
                        step.status = "PASSED"
                        step.completed_at = datetime.now(UTC)
                        step.workspace_fingerprint = observed
                        step.output_checksum = execution.runtime_checksum
                        step.artifact_ids = list(execution.artifact_ids or [])
                        step.updated_at = datetime.now(UTC)
                        binding.workspace_fingerprint = observed
                        binding.last_verified_fingerprint = observed
                        binding.last_verified_at = datetime.now(UTC)
                    steps.append(step)
            failed = [step.name for step in steps if step.status != "PASSED"]
            if failed:
                self._block(
                    session,
                    continuation,
                    "PROVEN_VALIDATION_NOT_AGGREGATEABLE",
                    "validation steps are not all passed: " + ", ".join(failed),
                )
                return
            store = self._artifact_store(session, continuation)
            payload = {
                "run_id": continuation.run_id,
                "stage_id": continuation.current_stage_id,
                "workspace_fingerprint": binding.workspace_fingerprint,
                "steps": {step.name: step.status for step in steps},
                "status": "PASS",
            }
            self._record_evidence(
                session,
                continuation,
                store,
                f"04_workflow_state/stages/{continuation.current_stage_id}/proven/validation-summary.json",
                payload,
                "validation-summary-v1",
            )
            self._advance_after(session, continuation, ProvenTransformationNode.AGGREGATE_PROVEN_VALIDATION.value)

    # -- Phase 7: promotion --------------------------------------------------

    def _node_promote_validated(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            if self._promotion is None:
                self._block(session, continuation, "PROVEN_PROMOTION_MISSING", "promotion service is not wired")
                return
            binding = self._binding(session, continuation)
            workspace = Path(binding.workspace_path)
            decision = self._promotion.promote_validated_generation(
                run_id=continuation.run_id,
                stage_id=continuation.current_stage_id,
                candidate_path=workspace,
                validation_summary=_promotion_summary(session, continuation),
            )
            if decision.status != "promoted":
                self._block(session, continuation, "PROVEN_PROMOTION_REJECTED", f"promotion rejected: {','.join(decision.blockers)}")
                return
            store = self._artifact_store(session, continuation)
            self._record_evidence(
                session,
                continuation,
                store,
                f"04_workflow_state/stages/{continuation.current_stage_id}/proven/promotion.json",
                decision.model_dump(mode="json"),
                "promotion-decision-v1",
            )
            self._advance_after(session, continuation, ProvenTransformationNode.PROMOTE_VALIDATED.value)

    def _node_promotion_pending(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            if self._sealing is None:
                self._block(session, continuation, "PROVEN_SEALING_MISSING", "sealing flow is not wired")
                return
            self._sealing.create_g12(continuation_id, worker_id)

    # -- failure normalization ----------------------------------------------

    def _failure_envelope_from_execution(
        self,
        session,
        continuation,
        execution,
        category: FailureCategory,
        phase: str,
    ) -> MigrationFailureEnvelope:
        stdout = ""
        stderr = ""
        if execution is not None:
            stdout = "".join(
                session.scalars(
                    select(CommandLogChunkModel.text)
                    .where(CommandLogChunkModel.execution_id == execution.id, CommandLogChunkModel.stream == "stdout")
                    .order_by(CommandLogChunkModel.sequence)
                )
            )
            stderr = "".join(
                session.scalars(
                    select(CommandLogChunkModel.text)
                    .where(CommandLogChunkModel.execution_id == execution.id, CommandLogChunkModel.stream == "stderr")
                    .order_by(CommandLogChunkModel.sequence)
                )
            )
        binding = self._binding(session, continuation) if continuation else None
        return envelope_from_execution(
            category=category,
            phase=phase,
            code=(execution.failure_code if execution else None) or "PROVEN_COMMAND_FAILED",
            message=(execution.failure_message if execution else None) or "proven command failed",
            command_id=execution.command_id if execution else None,
            execution_id=execution.id if execution else None,
            stdout=stdout,
            stderr=stderr,
            workspace=binding.workspace_path if binding else None,
            runtime=execution.runtime_profile_id if execution else None,
        )


# -- workspace helpers --------------------------------------------------------


def _clear_target_node_modules(
    binding: StageWorkspaceBindingModel,
    source_path: str | None,
    target_cohort: dict[str, str],
    *,
    source_family: str | None = None,
    target_family: str | None = None,
) -> None:
    """Rebuild target dependency inputs from source evidence before resolution."""
    import shutil

    workspace = Path(binding.workspace_path).resolve(strict=True)
    source = Path(source_path).resolve() if isinstance(source_path, str) else None
    package_lock = workspace / "package-lock.json"
    current_manifest = workspace / "package.json"
    try:
        current_lock = json.loads(package_lock.read_text(encoding="utf-8")) if package_lock.is_file() else {}
        current_values = json.loads(current_manifest.read_text(encoding="utf-8")) if current_manifest.is_file() else {}
    except (OSError, json.JSONDecodeError):
        current_lock = {}
        current_values = {}
    lock_root = current_lock.get("packages", {}).get("", {})
    targetized_lock = current_lock.get("lockfileVersion", 0) >= 2 and all(
        lock_root.get(section, {}).get(package) == exact
        for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies")
        for package, exact in target_cohort.items()
        if package in current_values.get(section, {})
    )
    node_modules = workspace / "node_modules"
    if node_modules.is_dir():
        shutil.rmtree(node_modules)
    if targetized_lock:
        return
    source_manifest = source / "package.json" if source is not None else None
    target_manifest = workspace / "package.json"
    if source_manifest is not None and source_manifest.is_file():
        manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
        for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
            values = manifest.get(section)
            if not isinstance(values, dict):
                continue
            for package, exact in target_cohort.items():
                if package in values:
                    values[package] = exact
        ProvenStageToolingPolicy().apply(
            manifest,
            str(source_family or ""),
            str(target_family or ""),
        )
        target_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    # The target lock is generated from the approved target manifest.  Copying
    # the source lock here preserves unrelated source resolutions; stale
    # Angular-family entries are removed before npm resolves the target cohort.
    if package_lock.is_file():
        package_lock.unlink()
    if source is not None:
        source_lock = source / "package-lock.json"
        if source_lock.is_file():
            shutil.copy2(source_lock, package_lock)
    if package_lock.is_file():
        lock = json.loads(package_lock.read_text(encoding="utf-8"))
        if lock.get("lockfileVersion") == 1 and isinstance(lock.get("dependencies"), dict):
            stale = tuple(
                name
                for name in lock["dependencies"]
                if name.startswith("@angular/")
                or name.startswith("@angular-devkit/")
                or name == "@ngtools/webpack"
            )
            for name in stale:
                lock["dependencies"].pop(name, None)
            package_lock.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _file_sha256(path: Path) -> str | None:
    import hashlib

    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _dependency_intent_from_workspace(workspace: Path) -> dict[str, object]:
    package_json = workspace / "package.json"
    payload: dict[str, object] = {}
    if package_json.is_file():
        import json as _json

        try:
            manifest = _json.loads(package_json.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}
        for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies", "peerDependenciesMeta"):
            payload[section] = manifest.get(section) or {}
    return {
        "workspace": str(workspace),
        "package_json_sha256": _file_sha256(package_json),
        "sections": payload,
    }


def _select_lock_authority(workspace: Path) -> tuple[str, str, str] | None:
    for filename, kind in (("npm-shrinkwrap.json", "SHRINKWRAP"), ("package-lock.json", "PACKAGE_LOCK")):
        candidate = workspace / filename
        if candidate.is_file():
            return filename, kind, _file_sha256(candidate) or "sha256:" + "0" * 64
    return None


def _apply_target_cohort(
    workspace: Path,
    cohort: dict[str, str],
    *,
    source_family: str | None = None,
    target_family: str | None = None,
) -> None:
    import json as _json

    package_json = workspace / "package.json"
    if not package_json.is_file():
        raise ProvenStageExecutionError("PROVEN_MANIFEST_MISSING", "package.json is missing")
    manifest = _json.loads(package_json.read_text(encoding="utf-8"))
    changed = False
    for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        current = manifest.get(section)
        if not isinstance(current, dict):
            continue
        for package, exact in cohort.items():
            if package in current and current[package] != exact:
                current[package] = exact
                changed = True
    changed = ProvenStageToolingPolicy().apply(
        manifest,
        str(source_family or ""),
        str(target_family or ""),
    ) or changed
    if changed:
        package_json.write_text(_json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _require_target_cohort(
    cohort: dict[str, str], *, source_family: str, target_family: str
) -> None:
    required = (
        "@angular/cli",
        "@angular/core",
        "@angular/animations",
        "@angular/common",
        "@angular/compiler",
        "@angular/compiler-cli",
        "@angular/forms",
        "@angular/platform-browser",
        "@angular/platform-browser-dynamic",
        "@angular/router",
        "@angular-devkit/build-angular",
        "typescript",
        "rxjs",
        "zone.js",
    )
    missing = [package for package in required if not cohort.get(package)]
    if missing:
        raise ProvenStageExecutionError(
            "PROVEN_TARGET_COHORT_INCOMPLETE",
            "approved target cohort is missing required package bindings",
            {
                "missing_packages": missing,
                "source_family": source_family,
                "target_family": target_family,
            },
        )


def _discover_migration_owners(workspace: Path) -> list[dict[str, str]]:
    package_json = workspace / "package.json"
    owners: list[dict[str, str]] = []
    if not package_json.is_file():
        return owners
    import json as _json

    try:
        manifest = _json.loads(package_json.read_text(encoding="utf-8"))
    except Exception:
        return owners
    sections = ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies")
    for section in sections:
        for package in (manifest.get(section) or {}):
            if package.startswith("@angular/"):
                owners.append({"package": package, "section": section})
    return owners


def _promotion_summary(session, continuation) -> object:
    """Derive the promotion summary from the persisted proven validation.

    The aggregate node already verified every validation step is PASSED and
    wrote the evidence artifact; promotion reuses that durable state instead
    of inventing a PASS summary here.
    """
    binding = _binding_row(session, continuation)
    stage_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
    plan = stage_plan.stage_plan if stage_plan is not None else {}
    group_by_check = {"build": "builds", "test": "tests", "lint": "lint"}
    required_groups = ["final_install"]
    for check in (plan.get("validation_policy") or {}).get("required_checks") or ("build", "test"):
        group = group_by_check.get(check)
        if group is not None and group not in required_groups:
            required_groups.append(group)
    steps = session.scalars(
        select(StageStepModel).where(
            StageStepModel.stage_id == continuation.current_stage_id,
            StageStepModel.name.in_(tuple(f"{group}-0" for group in required_groups)),
        )
    ).all()
    passed = steps and all(step.status == "PASSED" for step in steps)
    fingerprint = binding.workspace_fingerprint if binding is not None else "none"

    class _Summary:
        run_id = continuation.run_id
        stage_id = continuation.current_stage_id
        status = "PASS" if passed else "FAIL"
        candidate_fingerprint = fingerprint

    return _Summary()


def _binding_row(session, continuation) -> StageWorkspaceBindingModel | None:
    bindings = session.scalars(
        select(StageWorkspaceBindingModel).where(
            StageWorkspaceBindingModel.run_id == continuation.run_id,
            StageWorkspaceBindingModel.stage_id == continuation.current_stage_id,
            StageWorkspaceBindingModel.active.is_(True),
        )
        .order_by(
            StageWorkspaceBindingModel.created_at.desc(),
            StageWorkspaceBindingModel.id.desc(),
        )
    ).all()
    stage_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
    planned_aliases = {
        reference.get("working_directory_alias")
        for references in ((stage_plan.stage_plan or {}).get("commands") or {}).values()
        for reference in references
        if reference.get("working_directory_alias")
    }
    binding = next(
        (
            candidate
            for candidate in bindings
            if candidate.alias in planned_aliases
            and Path(candidate.workspace_path).is_dir()
            and StageSandboxCopier.fingerprint(Path(candidate.workspace_path))
            == candidate.workspace_fingerprint
        ),
        None,
    )
    if binding is not None:
        return binding
    return next(
        (
            candidate
            for candidate in bindings
            if Path(candidate.workspace_path).is_dir()
            and StageSandboxCopier.fingerprint(Path(candidate.workspace_path))
            == candidate.workspace_fingerprint
        ),
        bindings[0] if bindings else None,
    )
