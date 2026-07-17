"use client";

import { FormEvent, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { analyzeSource, refreshEnvironment, validatePaths } from "@/api/migrations";
import { ApiClientError, getBackendBaseUrl } from "@/api/client";
import { createProductionPreflight } from "@/api/preflights";
import type { PathValidationResult } from "@/types/generated/api";
import type { ProductionPreflight } from "@/types/preflight";
import styles from "./MigrationSetupForm.module.css";

type SetupInputs = {
  sourcePath: string;
  targetParentPath: string;
  targetAngularFamily: string;
  migrationMode: string;
};

const initialInputs: SetupInputs = {
  sourcePath: "",
  targetParentPath: "",
  targetAngularFamily: "21.x",
  migrationMode: "strict-functional-parity",
};

function inputKey(inputs: SetupInputs): string {
  return JSON.stringify(inputs);
}

function canStart(result: ProductionPreflight | null, currentKey: string, validatedKey: string | null): boolean {
  if (!result || currentKey !== validatedKey) return false;
  if (new Date(result.snapshot.expires_at).getTime() <= Date.now()) return false;
  return result.snapshot.status === "passed" || result.snapshot.status === "passed_with_warnings";
}

function idempotencyKey(scope: string, value: string): string {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return `${scope}-${(hash >>> 0).toString(36)}`;
}

type ValidationStage = "path validation" | "environment and source analysis" | "production preflight";

function isProductionPreflight(value: unknown): value is ProductionPreflight {
  if (!value || typeof value !== "object" || !("snapshot" in value)) return false;
  const snapshot = value.snapshot;
  return Boolean(
    snapshot && typeof snapshot === "object" &&
    "preflight_id" in snapshot && "status" in snapshot && "expires_at" in snapshot &&
    "input_checksum" in snapshot && "artifacts" in snapshot,
  );
}

function validationFailure(stage: ValidationStage, error: unknown): string {
  if (error instanceof ApiClientError) {
    const detail = error.responseBody ? `: ${error.responseBody}` : "";
    return `${stage} failed — ${error.method} ${error.path} returned ${error.status}${detail}`;
  }
  return `${stage} failed — ${error instanceof Error ? error.message : "unknown error"}`;
}
export function MigrationSetupForm() {
  const router = useRouter();
  const [inputs, setInputs] = useState(initialInputs);
  const [preflight, setPreflight] = useState<ProductionPreflight | null>(null);
  const [pathValidation, setPathValidation] = useState<PathValidationResult | null>(null);
  const [validatedKey, setValidatedKey] = useState<string | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [validationStage, setValidationStage] = useState<ValidationStage | null>(null);
  const validationAttempt = useRef(0);
  const currentKey = useMemo(() => inputKey(inputs), [inputs]);
  const startEnabled = canStart(preflight, currentKey, validatedKey);

  async function runPreflight() {
    const attempt = validationAttempt.current + 1;
    validationAttempt.current = attempt;
    const requestKey = currentKey;
    let activeStage: ValidationStage = "path validation";
    setValidationStage(activeStage);
    const pathKey = idempotencyKey("path-ui", JSON.stringify({ sourcePath: inputs.sourcePath, targetParentPath: inputs.targetParentPath, targetAngularFamily: inputs.targetAngularFamily }));
    setIsValidating(true);
    setError(null);
    setPreflight(null);
    setPathValidation(null);
    setValidatedKey(null);
    try {
      const pathResult = await validatePaths({
        source_path: inputs.sourcePath,
        target_parent_path: inputs.targetParentPath,
        target_angular_family: inputs.targetAngularFamily,
        idempotency_key: pathKey,
        actor: "control-tower",
      });
      if (validationAttempt.current !== attempt) return;
      setPathValidation(pathResult);
      if (pathResult.snapshot.status === "blocked") return;
      activeStage = "environment and source analysis";
      setValidationStage(activeStage);
      const [environment, analysis] = await Promise.all([
        refreshEnvironment({ idempotency_key: `environment-ui-${Date.now()}-${attempt}`, actor: "control-tower" }),
        analyzeSource({ source_path: pathResult.snapshot.source_path, idempotency_key: idempotencyKey("source-analysis-ui", pathResult.snapshot.source_path), actor: "control-tower" }),
      ]);
      if (validationAttempt.current !== attempt) return;
      activeStage = "production preflight";
      setValidationStage(activeStage);
      const result = await createProductionPreflight({
        path_validation_id: pathResult.snapshot.validation_id,
        environment_snapshot_id: environment.snapshot.snapshot_id,
        source_analysis_id: analysis.snapshot.analysis_id,
        target_angular_family: inputs.targetAngularFamily,
        migration_mode: inputs.migrationMode,
        idempotency_key: idempotencyKey("production-preflight-ui", JSON.stringify({ pathValidationId: pathResult.snapshot.validation_id, environmentSnapshotId: environment.snapshot.snapshot_id, sourceAnalysisId: analysis.snapshot.analysis_id, targetAngularFamily: inputs.targetAngularFamily, migrationMode: inputs.migrationMode })),
        actor: "control-tower",
      });
      if (validationAttempt.current !== attempt) return;
      if (!isProductionPreflight(result)) throw new Error("The production preflight response did not match the expected schema.");
      setPreflight(result);
      setValidatedKey(requestKey);
    } catch (error) {
      if (validationAttempt.current !== attempt) return;
      setError(validationFailure(activeStage, error));
    } finally {
      if (validationAttempt.current === attempt) {
        setValidationStage(null);
        setIsValidating(false);
      }
    }
  }

  async function startMigration(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!preflight || !startEnabled) return;
    setIsStarting(true);
    setError(null);
    try {
      router.push(`/preflights/${preflight.snapshot.preflight_id}`);
    } catch {
      setError("Start request failed.");
    } finally {
      setIsStarting(false);
    }
  }

  const artifact = preflight?.snapshot.artifacts["preflight_result.json"];
  const artifactHref = artifact ? `${getBackendBaseUrl()}/api/v1/artifacts/${artifact.artifact_id}` : null;
  const outputRootLabel = pathValidation?.snapshot.reservation_id
    ? "Reserved future output root (not created during validation)"
    : "Future output root preview (not created during validation)";

  return (
    <main className={styles.page}>
      <section className={styles.panel}>
        <p className={styles.kicker}>Control Tower</p>
        <h1>Prepare external migration</h1><p>The original application remains unchanged. Validation previews and reserves the external output root; run-owned files are created only after an approved migration run begins.</p>
        <form onSubmit={startMigration}>
          <label>
            Source path
            <input
              name="sourcePath"
              required
              placeholder="C:\\projects\\angular-18-app"
              value={inputs.sourcePath}
              onChange={(event) => setInputs({ ...inputs, sourcePath: event.target.value })}
            />
          </label>
          <label>
            External target-parent path
            <input
              name="targetParentPath"
              required
              placeholder="C:\\migration-results"
              value={inputs.targetParentPath}
              onChange={(event) => setInputs({ ...inputs, targetParentPath: event.target.value })}
            />
          </label>
          <label>
            Target Angular family
            <select
              name="targetAngularFamily"
              value={inputs.targetAngularFamily}
              onChange={(event) => setInputs({ ...inputs, targetAngularFamily: event.target.value })}
            >
              <option>21.x</option>
            </select>
          </label>
          <label>
            Migration mode
            <select
              name="migrationMode"
              value={inputs.migrationMode}
              onChange={(event) => setInputs({ ...inputs, migrationMode: event.target.value })}
            >
              <option value="strict-functional-parity">Strict functional parity</option>
            </select>
          </label>
          <div className={styles.actions}>
            <button type="button" onClick={runPreflight} disabled={isValidating || !inputs.sourcePath || !inputs.targetParentPath}>
              {isValidating ? "Validating" : "Validate"}
            </button>
            <button type="submit" disabled={!startEnabled || isStarting}>
              {isStarting ? "Starting" : "Start"}
            </button>
          </div>
        </form>
        {pathValidation && !preflight ? (
          <section className={styles.result} aria-label="Path validation result">
            <h2>Path validation</h2>
            <div><strong>{pathValidation.snapshot.status}</strong><span>{pathValidation.snapshot.checksum}</span></div>
            {pathValidation.snapshot.blockers.length > 0 ? <p>Blockers: {pathValidation.snapshot.blockers.join(", ")}</p> : null}
            {pathValidation.snapshot.warnings.length > 0 ? <p>Warnings: {pathValidation.snapshot.warnings.join(", ")}</p> : null}
            <p>{outputRootLabel}: {pathValidation.snapshot.resolved_output_root}</p>
            <p>Future migrated app (created after G14): {pathValidation.snapshot.resolved_output_root}\migrated-app</p>
            <p>Future migration workspace (created after an approved run begins): {pathValidation.snapshot.resolved_output_root}\.migration-factory</p>
            {pathValidation.snapshot.source_fingerprint ? <p>Source fingerprint: {pathValidation.snapshot.source_fingerprint}</p> : null}
          </section>
        ) : null}
        {preflight ? (
          <section className={styles.result} aria-label="Preflight result">
            <div><strong>{preflight.snapshot.status}</strong><span>{preflight.snapshot.input_checksum}</span></div>
            <p>Latest authoritative validation: {preflight.snapshot.preflight_id}</p>
            {preflight.snapshot.blockers.length > 0 ? <p>Blockers: {preflight.snapshot.blockers.join(", ")}</p> : null}
            {preflight.snapshot.warnings.length > 0 ? <p>Warnings: {preflight.snapshot.warnings.join(", ")}</p> : null}
            <p>{outputRootLabel}: {preflight.snapshot.resolved_output_root || pathValidation?.snapshot.resolved_output_root}</p>
            {artifactHref ? <a href={artifactHref}>Open preflight artifact</a> : null}
          </section>
        ) : null}
        {validationStage ? <p role="status">Validating {validationStage}…</p> : null}
        {error ? <p className={styles.error} role="alert">{error}</p> : null}
      </section>
    </main>
  );
}
