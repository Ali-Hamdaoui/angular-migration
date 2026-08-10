"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { analyzeSource, refreshEnvironment, validatePaths } from "@/api/migrations";
import type { SourceAnalysisResult } from "@/api/migrations";
import { ApiClientError } from "@/api/client";
import { createProductionPreflight } from "@/api/preflights";
import {
  buildSourceReviewSummary,
  environmentReadinessState,
  pathReadinessState,
  preflightReadinessState,
  readinessStateLabels,
  setupOperationRows,
  sourceReadinessState,
} from "@/presentation/setupReadiness";
import type { ReadinessState, SetupBinding, SetupOperation } from "@/presentation/setupReadiness";
import type { PathValidationResult } from "@/types/generated/api";
import type { ProductionPreflight } from "@/types/preflight";
import styles from "./MigrationSetupForm.module.css";

type SetupInputs = {
  sourcePath: string;
  targetParentPath: string;
  targetAngularFamily: string;
  migrationMode: string;
};

type OperationPresentation = {
  state: ReadinessState;
  supporting: string;
  messages: string[];
};

type OperationPresentations = Record<SetupOperation, OperationPresentation>;

const initialInputs: SetupInputs = {
  sourcePath: "",
  targetParentPath: "",
  targetAngularFamily: "21.x",
  migrationMode: "strict-functional-parity",
};

const pathFindingLabels: Readonly<Record<string, string>> = {
  SOURCE_PATH_NOT_ABSOLUTE: "Source path must be absolute.",
  SOURCE_PATH_NOT_FOUND: "Source path does not exist.",
  SOURCE_PATH_NOT_DIRECTORY: "Source path must be a directory.",
  SOURCE_PATH_NOT_READABLE: "Source path is not readable.",
  TARGET_PARENT_NOT_ABSOLUTE: "Target parent path must be absolute.",
  TARGET_PARENT_NOT_DIRECTORY: "Target parent must be an existing directory or safely creatable.",
  TARGET_PARENT_NOT_WRITABLE: "Target parent or its nearest existing parent is not writable.",
  SOURCE_TARGET_EQUAL: "Source and target parent must be different.",
  TARGET_PARENT_INSIDE_SOURCE: "Target parent must not be inside the source project.",
  SOURCE_INSIDE_TARGET_PARENT: "Source project must not be inside the target parent.",
  OUTPUT_ROOT_INSIDE_SOURCE: "Generated output would be inside the source project.",
  SOURCE_INSIDE_OUTPUT_ROOT: "Source project would be inside the generated output.",
  SOURCE_OUTSIDE_ALLOWED_ROOTS: "Source is outside configured roots; this is advisory only.",
  TARGET_PARENT_OUTSIDE_ALLOWED_ROOTS: "Target parent is outside configured roots; this is advisory only.",
  OUTPUT_ROOT_OUTSIDE_ALLOWED_ROOTS: "Generated output is outside configured roots; this is advisory only.",
};

function initialOperations(): OperationPresentations {
  return {
    path: { state: "waiting", supporting: setupOperationRows[0].waitingCopy, messages: [] },
    environment: { state: "waiting", supporting: setupOperationRows[1].waitingCopy, messages: [] },
    source: { state: "waiting", supporting: setupOperationRows[2].waitingCopy, messages: [] },
    preflight: { state: "waiting", supporting: setupOperationRows[3].waitingCopy, messages: [] },
  };
}

function operationIdempotencyKey(scope: string): string {
  const operation = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `${scope}-${operation}`;
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isArtifactMap(value: unknown): boolean {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  return Object.values(value as Record<string, unknown>).every((artifact) => {
    if (!artifact || typeof artifact !== "object" || Array.isArray(artifact)) return false;
    const candidate = artifact as Record<string, unknown>;
    return typeof candidate.artifact_id === "string" && candidate.artifact_id.length > 0 &&
      typeof candidate.checksum === "string" && candidate.checksum.length > 0 &&
      typeof candidate.relative_path === "string" && candidate.relative_path.length > 0;
  });
}

function isDecisionHistory(value: unknown, preflightId: string, gateId: string): boolean {
  if (!Array.isArray(value)) return false;
  const decisions = new Set(["approved", "approved_with_comment", "modification_requested", "rejected"]);
  return value.every((item) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) return false;
    const candidate = item as Record<string, unknown>;
    return typeof candidate.decision_id === "string" && candidate.decision_id.length > 0 &&
      candidate.preflight_id === preflightId &&
      candidate.gate_id === gateId &&
      typeof candidate.decision === "string" && decisions.has(candidate.decision) &&
      typeof candidate.actor === "string" && candidate.actor.length > 0 &&
      (candidate.comment === null || typeof candidate.comment === "string") &&
      typeof candidate.decided_at === "string" && Number.isFinite(Date.parse(candidate.decided_at)) &&
      typeof candidate.input_checksum === "string" && candidate.input_checksum.length > 0 &&
      typeof candidate.artifact_set_checksum === "string" && candidate.artifact_set_checksum.length > 0 &&
      Number.isInteger(candidate.state_version) && (candidate.state_version as number) >= 1 &&
      typeof candidate.idempotent_replay === "boolean";
  });
}

function isProductionPreflight(value: unknown): value is ProductionPreflight {
  if (!value || typeof value !== "object" || !("snapshot" in value)) return false;
  const snapshot = value.snapshot;
  if (!snapshot || typeof snapshot !== "object") return false;
  const candidate = snapshot as Record<string, unknown>;
  const statuses = new Set(["passed", "passed_with_warnings", "blocked", "expired", "stale"]);
  const approvalStatuses = new Set(["pending", "approved", "approved_with_comment", "modification_requested", "rejected", "expired", "stale"]);
  const stringFields = [
    "preflight_id", "gate_id", "gate_version", "created_at", "expires_at", "input_checksum",
    "artifact_set_checksum", "target_angular_family", "migration_mode", "source_path",
    "target_parent_path", "generated_output_name", "resolved_output_root", "platform_repository_root",
    "target_output_path", "approval_status",
  ];
  return (
    stringFields.every((field) => typeof candidate[field] === "string") &&
    (candidate.preflight_id as string).length > 0 &&
    candidate.gate_id === "G01" &&
    (candidate.gate_version as string).length > 0 &&
    Number.isInteger(candidate.state_version) && (candidate.state_version as number) >= 1 &&
    typeof candidate.status === "string" && statuses.has(candidate.status) &&
    typeof candidate.approval_status === "string" && approvalStatuses.has(candidate.approval_status) &&
    Number.isFinite(Date.parse(candidate.created_at as string)) &&
    typeof candidate.expires_at === "string" && Number.isFinite(Date.parse(candidate.expires_at)) &&
    typeof candidate.input_checksum === "string" && candidate.input_checksum.length > 0 &&
    typeof candidate.artifact_set_checksum === "string" && candidate.artifact_set_checksum.length > 0 &&
    (candidate.target_reservation_id === null || typeof candidate.target_reservation_id === "string") &&
    isStringArray(candidate.blockers) &&
    isStringArray(candidate.warnings) &&
    isArtifactMap(candidate.artifacts) &&
    isDecisionHistory(candidate.decision_history, candidate.preflight_id as string, candidate.gate_id as string)
  );
}

function requestFailure(stage: string, error: unknown): string {
  if (error instanceof ApiClientError) {
    const detail = error.responseBody ? `: ${error.responseBody}` : "";
    return `${stage} failed: ${error.method} ${error.path} returned ${error.status}${detail}`;
  }
  return `${stage} failed: ${error instanceof Error ? error.message : "unknown error"}`;
}

function pathMessage(result: PathValidationResult, code: string): string {
  return result.snapshot.rules.find((rule) => rule.code === code)?.message ?? pathFindingLabels[code] ?? code;
}

function translatedPathMessages(result: PathValidationResult): string[] {
  return [...result.snapshot.blockers, ...result.snapshot.warnings].map((code) => pathMessage(result, code));
}

function verbatimMessages(blockers: string[], warnings: string[]): string[] {
  return [...blockers, ...warnings];
}

function isActionableState(state: ReadinessState): boolean {
  return state === "passed" || state === "warning";
}

function completedSupporting(status: string, identifier: string): string {
  return `Backend status: ${status}. Evidence identifier: ${identifier}.`;
}

function markOperationsOutdated(current: OperationPresentations): OperationPresentations {
  function mark(id: SetupOperation): OperationPresentation {
    const operation = current[id];
    const row = setupOperationRows.find((candidate) => candidate.id === id);
    if (!row || operation.state === "waiting") return operation;
    return {
      ...operation,
      state: "outdated",
      supporting: `Previous ${row.label.toLowerCase()} evidence is outdated because the Project configuration changed.`,
    };
  }
  return {
    path: mark("path"),
    environment: mark("environment"),
    source: mark("source"),
    preflight: mark("preflight"),
  };
}

export function MigrationSetupForm() {
  const router = useRouter();
  const [inputs, setInputs] = useState(initialInputs);
  const [configurationRevision, setConfigurationRevision] = useState(0);
  const configurationRevisionRef = useRef(0);
  const requestAttemptRef = useRef(0);
  const [operations, setOperations] = useState<OperationPresentations>(initialOperations);
  const [pathValidation, setPathValidation] = useState<PathValidationResult | null>(null);
  const [sourceAnalysis, setSourceAnalysis] = useState<SourceAnalysisResult | null>(null);
  const [activeBinding, setActiveBinding] = useState<SetupBinding | null>(null);
  const activeBindingRef = useRef<SetupBinding | null>(null);
  const [hasChecked, setHasChecked] = useState(false);
  const [isChecking, setIsChecking] = useState(false);
  const [configurationChanged, setConfigurationChanged] = useState(false);
  const [liveMessage, setLiveMessage] = useState("");
  const [requestAlert, setRequestAlert] = useState<string | null>(null);

  function handleProjectChange(field: keyof SetupInputs, value: string) {
    if (inputs[field] === value) return;
    const nextRevision = configurationRevisionRef.current + 1;
    configurationRevisionRef.current = nextRevision;
    requestAttemptRef.current += 1;
    setConfigurationRevision(nextRevision);
    setInputs((current) => ({ ...current, [field]: value }));
    setIsChecking(false);
    activeBindingRef.current = null;
    setActiveBinding(null);
    setRequestAlert(null);
    if (hasChecked || isChecking) {
      setOperations(markOperationsOutdated);
      setConfigurationChanged(true);
      setLiveMessage("Configuration changed. Previous readiness evidence is outdated.");
    }
  }

  function requestIsCurrent(attempt: number, revision: number): boolean {
    return requestAttemptRef.current === attempt && configurationRevisionRef.current === revision;
  }

  useEffect(() => {
    if (!activeBinding) return;
    const binding = activeBinding;
    let expiryTimer: ReturnType<typeof setTimeout> | undefined;
    let cancelled = false;

    function scheduleAuthoritativeExpiry() {
      if (cancelled) return;
      const remaining = Date.parse(binding.expiresAt) - Date.now();
      if (remaining > 0) {
        expiryTimer = setTimeout(scheduleAuthoritativeExpiry, Math.min(remaining, 2_147_483_647));
        return;
      }
      if (activeBindingRef.current?.preflightId !== binding.preflightId ||
        activeBindingRef.current.revision !== binding.revision) return;
      activeBindingRef.current = null;
      setActiveBinding(null);
      setOperations((current) => ({
        ...current,
        preflight: {
          ...current.preflight,
          state: "outdated",
          supporting: "The authoritative production preflight has expired. Check readiness again.",
        },
      }));
      setLiveMessage("Production preflight expired. Check readiness again.");
    }

    scheduleAuthoritativeExpiry();
    return () => {
      cancelled = true;
      if (expiryTimer !== undefined) clearTimeout(expiryTimer);
    };
  }, [activeBinding]);

  function reviewProductionReadiness() {
    const binding = activeBindingRef.current;
    if (!binding || binding.revision !== configurationRevisionRef.current) return;
    if (Date.parse(binding.expiresAt) <= Date.now()) {
      activeBindingRef.current = null;
      setActiveBinding(null);
      setOperations((current) => ({
        ...current,
        preflight: {
          ...current.preflight,
          state: "outdated",
          supporting: "The authoritative production preflight has expired. Check readiness again.",
        },
      }));
      setLiveMessage("Production preflight expired. Check readiness again.");
      return;
    }
    router.push(`/preflights/${binding.preflightId}`);
  }

  async function runReadiness() {
    const requestRevision = configurationRevisionRef.current;
    const attempt = requestAttemptRef.current + 1;
    requestAttemptRef.current = attempt;
    const currentInputs = {
      sourcePath: inputs.sourcePath.trim(),
      targetParentPath: inputs.targetParentPath.trim(),
      targetAngularFamily: inputs.targetAngularFamily.trim(),
      migrationMode: inputs.migrationMode.trim(),
    };
    const operationKey = operationIdempotencyKey(`setup-revision-${requestRevision}`);

    setHasChecked(true);
    setIsChecking(true);
    setConfigurationChanged(false);
    setRequestAlert(null);
    activeBindingRef.current = null;
    setActiveBinding(null);
    setPathValidation(null);
    setSourceAnalysis(null);
    setOperations({
      ...initialOperations(),
      path: {
        state: "running",
        supporting: setupOperationRows[0].runningCopy,
        messages: [],
      },
    });
    setLiveMessage("Checking path safety and target reservation.");

    try {
      if (!currentInputs.sourcePath || !currentInputs.targetParentPath) {
        setOperations((current) => ({
          ...current,
          path: { state: "unavailable", supporting: "Enter both required paths before checking readiness.", messages: [] },
        }));
        setRequestAlert("Readiness request failed. Enter both a source path and an external target-parent path.");
        return;
      }

      let pathResult: PathValidationResult;
      try {
        pathResult = await validatePaths({
          source_path: currentInputs.sourcePath,
          target_parent_path: currentInputs.targetParentPath,
          target_angular_family: currentInputs.targetAngularFamily,
          idempotency_key: `${operationKey}:path`,
          actor: "control-tower",
        });
      } catch (error) {
        if (!requestIsCurrent(attempt, requestRevision)) return;
        setOperations((current) => ({
          ...current,
          path: { state: "unavailable", supporting: requestFailure("Path validation", error), messages: [] },
        }));
        setRequestAlert("Readiness request failed. Path safety is unavailable.");
        return;
      }

      if (!requestIsCurrent(attempt, requestRevision)) return;
      const pathState = pathReadinessState(pathResult.snapshot.status);
      setPathValidation(pathResult);
      setOperations((current) => ({
        ...current,
        path: {
          state: pathState,
          supporting: pathResult.snapshot.target_reservation_eligible
            ? completedSupporting(pathResult.snapshot.status, pathResult.snapshot.validation_id)
            : "The returned path evidence is not eligible for a target reservation.",
          messages: translatedPathMessages(pathResult),
        },
      }));

      if (pathResult.snapshot.status === "blocked" || !pathResult.snapshot.target_reservation_eligible) {
        if (!requestIsCurrent(attempt, requestRevision)) return;
        setLiveMessage("Path safety completed with a blocker. Correct the Project configuration before continuing.");
        return;
      }

      if (!requestIsCurrent(attempt, requestRevision)) return;
      setOperations((current) => ({
        ...current,
        environment: { state: "running", supporting: setupOperationRows[1].runningCopy, messages: [] },
        source: { state: "running", supporting: setupOperationRows[2].runningCopy, messages: [] },
      }));
      setLiveMessage("Path safety completed. Checking environment capability and source analysis in parallel.");

      const [environmentSettled, sourceSettled] = await Promise.allSettled([
        refreshEnvironment({ idempotency_key: `${operationKey}:environment`, actor: "control-tower" }),
        analyzeSource({
          source_path: pathResult.snapshot.source_path,
          idempotency_key: `${operationKey}:source-analysis`,
          actor: "control-tower",
        }),
      ]);

      if (!requestIsCurrent(attempt, requestRevision)) return;
      const environmentResult = environmentSettled.status === "fulfilled" ? environmentSettled.value : null;
      const sourceResult = sourceSettled.status === "fulfilled" ? sourceSettled.value : null;
      const environmentState = environmentResult
        ? environmentReadinessState(environmentResult.snapshot.status)
        : "unavailable";
      const sourceState = sourceResult
        ? sourceReadinessState(sourceResult.snapshot.status)
        : "unavailable";
      setSourceAnalysis(sourceResult);
      setOperations((current) => ({
        ...current,
        environment: environmentResult ? {
          state: environmentState,
          supporting: completedSupporting(environmentResult.snapshot.status, environmentResult.snapshot.snapshot_id),
          messages: verbatimMessages(environmentResult.snapshot.blockers, environmentResult.snapshot.warnings),
        } : {
          state: "unavailable",
          supporting: requestFailure("Environment capability", environmentSettled.status === "rejected" ? environmentSettled.reason : null),
          messages: [],
        },
        source: sourceResult ? {
          state: sourceState,
          supporting: completedSupporting(sourceResult.snapshot.status, sourceResult.snapshot.analysis_id),
          messages: verbatimMessages(sourceResult.snapshot.blockers, sourceResult.snapshot.warnings),
        } : {
          state: "unavailable",
          supporting: requestFailure("Source analysis", sourceSettled.status === "rejected" ? sourceSettled.reason : null),
          messages: [],
        },
      }));

      if (!environmentResult || !sourceResult) {
        if (!requestIsCurrent(attempt, requestRevision)) return;
        setRequestAlert(`Readiness request failed. ${!environmentResult ? "Environment capability" : "Source analysis"} is unavailable.`);
        setLiveMessage("Readiness stopped because required evidence is unavailable.");
        return;
      }

      if (!requestIsCurrent(attempt, requestRevision)) return;
      setOperations((current) => ({
        ...current,
        preflight: { state: "running", supporting: setupOperationRows[3].runningCopy, messages: [] },
      }));
      setLiveMessage("Environment and source evidence completed. Creating production preflight.");

      let preflightResponse: unknown;
      try {
        preflightResponse = await createProductionPreflight({
          path_validation_id: pathResult.snapshot.validation_id,
          environment_snapshot_id: environmentResult.snapshot.snapshot_id,
          source_analysis_id: sourceResult.snapshot.analysis_id,
          target_angular_family: currentInputs.targetAngularFamily,
          migration_mode: currentInputs.migrationMode,
          idempotency_key: `${operationKey}:production-preflight`,
          actor: "control-tower",
        });
      } catch (error) {
        if (!requestIsCurrent(attempt, requestRevision)) return;
        setOperations((current) => ({
          ...current,
          preflight: { state: "unavailable", supporting: requestFailure("Production preflight", error), messages: [] },
        }));
        setRequestAlert("Readiness request failed. Production preflight is unavailable.");
        return;
      }

      if (!requestIsCurrent(attempt, requestRevision)) return;
      if (!isProductionPreflight(preflightResponse)) {
        setOperations((current) => ({
          ...current,
          preflight: {
            state: "unavailable",
            supporting: "The production preflight response did not match the authoritative schema.",
            messages: [],
          },
        }));
        setRequestAlert("Readiness request failed. Production preflight is unavailable.");
        return;
      }

      const returnedPreflight = preflightResponse;
      const responseExpired = Date.parse(returnedPreflight.snapshot.expires_at) <= Date.now();
      const preflightState = preflightReadinessState(
        returnedPreflight.snapshot.status,
        responseExpired && (returnedPreflight.snapshot.status === "passed" || returnedPreflight.snapshot.status === "passed_with_warnings")
          ? "outdated"
          : undefined,
      );
      if (!requestIsCurrent(attempt, requestRevision)) return;
      setOperations((current) => ({
        ...current,
        preflight: {
          state: preflightState,
          supporting: completedSupporting(returnedPreflight.snapshot.status, returnedPreflight.snapshot.preflight_id),
          messages: verbatimMessages(returnedPreflight.snapshot.blockers, returnedPreflight.snapshot.warnings),
        },
      }));

      const actionable = (
        !responseExpired &&
        isActionableState(pathState) &&
        isActionableState(environmentState) &&
        isActionableState(sourceState) &&
        isActionableState(preflightState)
      );
      if (actionable) {
        if (!requestIsCurrent(attempt, requestRevision)) return;
        const binding: SetupBinding = {
          revision: requestRevision,
          pathValidationId: pathResult.snapshot.validation_id,
          environmentSnapshotId: environmentResult.snapshot.snapshot_id,
          sourceAnalysisId: sourceResult.snapshot.analysis_id,
          preflightId: returnedPreflight.snapshot.preflight_id,
          expiresAt: returnedPreflight.snapshot.expires_at,
        };
        activeBindingRef.current = binding;
        setActiveBinding(binding);
      }
      if (!requestIsCurrent(attempt, requestRevision)) return;
      setLiveMessage("Readiness check finished with authoritative evidence.");
    } finally {
      if (requestIsCurrent(attempt, requestRevision)) {
        setIsChecking(false);
      }
    }
  }

  const sourceReview = sourceAnalysis ? buildSourceReviewSummary(sourceAnalysis, pathValidation) : null;
  const operationStates = Object.values(operations).map((operation) => operation.state);
  const isOutdated = operationStates.some((state) => state === "outdated");
  const isBlocked = (
    pathValidation !== null && !pathValidation.snapshot.target_reservation_eligible
  ) || operationStates.some((state) => state === "blocked");
  const isUnavailable = operationStates.some((state) => state === "unavailable");
  const hasWarning = operationStates.some((state) => state === "warning");
  const hasPassedPreflight = operations.preflight.state === "passed" || operations.preflight.state === "warning";
  const readinessSummary = isChecking
    ? null
    : isOutdated
      ? "Previous readiness evidence is outdated"
      : isBlocked
        ? "Readiness checks are blocked"
        : isUnavailable
          ? "Readiness checks could not be completed"
          : hasPassedPreflight
            ? hasWarning ? "Readiness checks completed with warnings" : "Readiness checks passed"
            : null;

  const journeyStates = {
    project: isChecking ? "Completed; readiness is running" : "Current",
    readiness: isChecking ? "Current" : hasChecked ? isOutdated ? "Outdated" : "Completed" : "Waiting",
    sourceReview: sourceAnalysis ? isOutdated ? "Outdated" : "Available" : "Locked",
    createRun: "Locked pending production readiness review and approval",
  };

  const targetBoundary = pathValidation?.snapshot.resolved_output_root || "the reserved external target shown after readiness";

  return (
    <main className={styles.page}>
      <div className={styles.shell}>
        <header className={styles.header}>
          <p className={styles.kicker}>Migration preparation</p>
          <h1>Prepare an authoritative migration</h1>
          <p>Verify the read-only source boundary, collect readiness evidence, and hand the exact production preflight to the production readiness review.</p>
        </header>

        <nav className={styles.journey} aria-label="Migration preparation journey">
          <ol aria-label="Migration preparation steps">
            <li><span>1</span><strong>Project</strong><small>{journeyStates.project}</small></li>
            <li><span>2</span><strong>Readiness</strong><small>{journeyStates.readiness}</small></li>
            <li><span>3</span><strong>Source review</strong><small>{journeyStates.sourceReview}</small></li>
            <li><span>4</span><strong>Create run</strong><small>{journeyStates.createRun}</small></li>
          </ol>
        </nav>

        <section className={styles.section} aria-labelledby="project-heading">
          <div className={styles.sectionHeading}>
            <div><p className={styles.stepLabel}>Step 1</p><h2 id="project-heading">Project</h2></div>
            <span className={styles.revision}>Configuration revision {configurationRevision}</span>
          </div>
          <p>The source remains read-only. Generated output is run-owned and must stay outside the source project.</p>
          <form className={styles.projectForm} onSubmit={(event) => event.preventDefault()}>
            <label>
              Source path
              <input
                name="sourcePath"
                required
                value={inputs.sourcePath}
                placeholder="C:\\projects\\angular-20-app"
                onChange={(event) => handleProjectChange("sourcePath", event.target.value)}
              />
            </label>
            <label>
              External target-parent path
              <input
                name="targetParentPath"
                required
                value={inputs.targetParentPath}
                placeholder="C:\\migration-results"
                onChange={(event) => handleProjectChange("targetParentPath", event.target.value)}
              />
            </label>
            <label>
              Target Angular family
              <select
                name="targetAngularFamily"
                value={inputs.targetAngularFamily}
                onChange={(event) => handleProjectChange("targetAngularFamily", event.target.value)}
              >
                <option value="21.x">21.x</option>
              </select>
            </label>
            <label>
              Migration mode
              <select
                name="migrationMode"
                value={inputs.migrationMode}
                onChange={(event) => handleProjectChange("migrationMode", event.target.value)}
              >
                <option value="strict-functional-parity">Strict functional parity</option>
              </select>
            </label>
          </form>
          <div className={styles.actions}>
            <button type="button" onClick={runReadiness} disabled={isChecking}>
              {isChecking ? "Checking readiness" : hasChecked ? "Check readiness again" : "Check readiness"}
            </button>
          </div>
        </section>

        <section className={styles.section} aria-labelledby="readiness-heading">
          <div className={styles.sectionHeading}>
            <div><p className={styles.stepLabel}>Step 2</p><h2 id="readiness-heading">Readiness</h2></div>
          </div>
          {readinessSummary ? <p className={styles.summary} data-state={isBlocked ? "blocked" : hasWarning ? "warning" : isOutdated ? "outdated" : "passed"}>{readinessSummary}</p> : null}
          <ul className={styles.operationList} aria-label="Readiness operations">
            {setupOperationRows.map((row) => {
              const operation = operations[row.id];
              return (
                <li key={row.id} aria-label={row.label} data-state={operation.state}>
                  <div className={styles.operationHeading}>
                    <h3>{row.label}</h3>
                    <span>{readinessStateLabels[operation.state]}</span>
                  </div>
                  <p>{operation.supporting}</p>
                  {operation.messages.length > 0 ? <ul>{operation.messages.map((message) => <li key={message}>{message}</li>)}</ul> : null}
                </li>
              );
            })}
          </ul>
        </section>

        <section className={styles.section} aria-labelledby="source-review-heading">
          <div className={styles.sectionHeading}>
            <div><p className={styles.stepLabel}>Step 3</p><h2 id="source-review-heading">Source review</h2></div>
            {sourceAnalysis ? <span className={styles.evidenceState}>{isOutdated ? "Outdated evidence" : "Readiness evidence"}</span> : null}
          </div>
          {sourceReview ? (
            <>
              <dl className={styles.evidenceGrid}>
                <div><dt>Detected Angular version</dt><dd>{sourceReview.angularVersion}</dd></div>
                <div><dt>Workspace topology</dt><dd>{sourceReview.workspaceTopology}</dd></div>
                <div><dt>Package manager</dt><dd>{sourceReview.packageManager}</dd></div>
                <div><dt>Project count</dt><dd>{sourceReview.projectCount}</dd></div>
                <div><dt>Builder name</dt><dd>{sourceReview.builderName}</dd></div>
                <div><dt>Custom builder detected</dt><dd>{sourceReview.customBuilderDetected}</dd></div>
                <div><dt>Lockfile</dt><dd>{sourceReview.lockfile}</dd></div>
                <div><dt>Evidence confidence</dt><dd>{sourceReview.evidenceConfidence}</dd></div>
                <div className={styles.wideEvidence}><dt>Reserved target</dt><dd>{sourceReview.reservedTarget}</dd></div>
              </dl>
              {sourceReview.warnings.length > 0 ? (
                <div className={styles.findings}><h3>Source warnings</h3><ul>{sourceReview.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></div>
              ) : <p>No source-analysis warnings were returned.</p>}
              {activeBinding ? (
                <button type="button" className={styles.reviewAction} onClick={reviewProductionReadiness}>
                  Review production readiness
                </button>
              ) : null}
            </>
          ) : <p>Source evidence becomes available after path, environment, and source readiness requests complete.</p>}
        </section>

        <section className={`${styles.section} ${styles.lockedSection}`} aria-labelledby="create-run-heading">
          <div className={styles.sectionHeading}>
            <div><p className={styles.stepLabel}>Step 4</p><h2 id="create-run-heading">Create run</h2></div>
            <span className={styles.lockedLabel}>Locked pending production readiness approval</span>
          </div>
          <p>Production readiness review and approval on the production readiness route unlocks authoritative run creation. This setup page does not approve production readiness and does not create a run.</p>
          <p>The source remains read-only. After approval, run-owned output is created only under <strong className={styles.technical}>{targetBoundary}</strong>.</p>
        </section>

        <p className={styles.liveStatus} role="status" aria-live="polite">
          {configurationChanged ? "Configuration changed. Previous readiness evidence is outdated." : liveMessage}
        </p>
        {requestAlert ? <p className={styles.alert} role="alert">{requestAlert}</p> : null}
      </div>
    </main>
  );
}
