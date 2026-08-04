"use client";

import { FormEvent, useRef, useState } from "react";
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

function operationIdempotencyKey(scope: string): string {
  const operation = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `${scope}-${operation}`;
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
  const formRef = useRef<HTMLFormElement>(null);
  const [inputs, setInputs] = useState(initialInputs);
  const [preflight, setPreflight] = useState<ProductionPreflight | null>(null);
  const [pathValidation, setPathValidation] = useState<PathValidationResult | null>(null);
  const [validatedKey, setValidatedKey] = useState<string | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [validationStage, setValidationStage] = useState<ValidationStage | null>(null);
  const validationAttempt = useRef(0);
  const currentKey = inputKey(inputs);
  const startEnabled = canStart(preflight, currentKey, validatedKey);

  function readLiveInputs(): SetupInputs {
    const form = formRef.current;
    const data = form ? new FormData(form) : null;
    return {
      sourcePath: String(data?.get("sourcePath") ?? "").trim(),
      targetParentPath: String(data?.get("targetParentPath") ?? "").trim(),
      targetAngularFamily: String(data?.get("targetAngularFamily") ?? initialInputs.targetAngularFamily).trim(),
      migrationMode: String(data?.get("migrationMode") ?? initialInputs.migrationMode).trim(),
    };
  }

  function invalidatePreflight(nextInputs: SetupInputs) {
    setInputs(nextInputs);
    setPreflight(null);
    setPathValidation(null);
    setValidatedKey(null);
  }

  async function runPreflight() {
    const liveInputs = readLiveInputs();
    const requestKey = inputKey(liveInputs);
    setInputs(liveInputs);
    const attempt = validationAttempt.current + 1;
    validationAttempt.current = attempt;
    let activeStage: ValidationStage = "path validation";
    setValidationStage(activeStage);
    // A new explicit validation must re-check the filesystem. Including the
    // attempt distinguishes it from an earlier persisted validation for the
    // same paths, which may have been blocked by a folder that was later
    // removed or renamed.
    const operationKey = operationIdempotencyKey("validate-ui");
    const pathKey = `${operationKey}:path`;
    setIsValidating(true);
    setError(null);
    setPreflight(null);
    setPathValidation(null);
    setValidatedKey(null);
    try {
      if (!liveInputs.sourcePath || !liveInputs.targetParentPath) {
        setError("Enter both a source path and an external target-parent path.");
        return;
      }
      const pathResult = await validatePaths({
        source_path: liveInputs.sourcePath,
        target_parent_path: liveInputs.targetParentPath,
        target_angular_family: liveInputs.targetAngularFamily,
        idempotency_key: pathKey,
        actor: "control-tower",
      });
      if (validationAttempt.current !== attempt) return;
      setPathValidation(pathResult);
      if (pathResult.snapshot.status === "blocked") return;
      activeStage = "environment and source analysis";
      setValidationStage(activeStage);
      const [environment, analysis] = await Promise.all([
        refreshEnvironment({ idempotency_key: `${operationKey}:environment`, actor: "control-tower" }),
        analyzeSource({ source_path: pathResult.snapshot.source_path, idempotency_key: `${operationKey}:source-analysis`, actor: "control-tower" }),
      ]);
      if (validationAttempt.current !== attempt) return;
      activeStage = "production preflight";
      setValidationStage(activeStage);
      const result = await createProductionPreflight({
        path_validation_id: pathResult.snapshot.validation_id,
        environment_snapshot_id: environment.snapshot.snapshot_id,
        source_analysis_id: analysis.snapshot.analysis_id,
        target_angular_family: liveInputs.targetAngularFamily,
        migration_mode: liveInputs.migrationMode,
        idempotency_key: `${operationKey}:production-preflight`,
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
        <p className={styles.kicker}>New migration</p>
        <h1>Set up Angular migration</h1><p>The original application remains unchanged. Validation previews and reserves the output folder; migration files are created only after an approved migration run begins.</p>
        <form ref={formRef} onSubmit={startMigration}>
          <label>
            Source application folder
            <input
              name="sourcePath"
              required
              defaultValue={initialInputs.sourcePath}
              placeholder="C:\\projects\\angular-18-app"
              onInput={(event) => invalidatePreflight({ ...readLiveInputs(), sourcePath: event.currentTarget.value })}
              onChange={(event) => invalidatePreflight({ ...readLiveInputs(), sourcePath: event.currentTarget.value })}
            />
          </label>
          <label>
            Output folder
            <input
              name="targetParentPath"
              required
              defaultValue={initialInputs.targetParentPath}
              placeholder="C:\\migration-results"
              onInput={(event) => invalidatePreflight({ ...readLiveInputs(), targetParentPath: event.currentTarget.value })}
              onChange={(event) => invalidatePreflight({ ...readLiveInputs(), targetParentPath: event.currentTarget.value })}
            />
            <small>The migrated application and migration workspace will be created inside the selected output location only after approval.</small>
          </label>
          <label>
            Target Angular version
            <select
              name="targetAngularFamily"
              defaultValue={initialInputs.targetAngularFamily}
              onChange={(event) => invalidatePreflight({ ...readLiveInputs(), targetAngularFamily: event.target.value })}
            >
              <option>21.x</option>
            </select>
          </label>
          <label>
            Migration strategy
            <select
              name="migrationMode"
              defaultValue={initialInputs.migrationMode}
              onChange={(event) => invalidatePreflight({ ...readLiveInputs(), migrationMode: event.target.value })}
            >
              <option value="strict-functional-parity">Preserve current behavior</option>
            </select>
          </label>
          <div className={styles.actions}>
            <button type="button" onClick={runPreflight} disabled={isValidating}>
              {isValidating ? "Validating" : "Validate paths"}
            </button>
            <button type="submit" disabled={!startEnabled || isStarting}>
              {isStarting ? "Starting" : "Start migration"}
            </button>
          </div>
        </form>
        {pathValidation && !preflight ? (
          <section className={styles.result} aria-label="Path check result">
            <h2>Path check</h2>
            <div><strong>{pathValidation.snapshot.status}</strong><span>{pathValidation.snapshot.checksum}</span></div>
            {pathValidation.snapshot.blockers.length > 0 ? <p>Blocking issues: {pathValidation.snapshot.blockers.join(", ")}</p> : null}
            {pathValidation.snapshot.warnings.length > 0 ? <p>Warnings: {pathValidation.snapshot.warnings.join(", ")}</p> : null}
            <p>{outputRootLabel}: {pathValidation.snapshot.resolved_output_root}</p>
            <p>Future migrated app (created after G14): {pathValidation.snapshot.resolved_output_root}\migrated-app</p>
            <p>Future migration workspace (created after an approved run begins): {pathValidation.snapshot.resolved_output_root}\.migration-factory</p>
            {pathValidation.snapshot.source_fingerprint ? <p>Source fingerprint: {pathValidation.snapshot.source_fingerprint}</p> : null}
          </section>
        ) : null}
        {preflight ? (
          <section className={styles.result} aria-label="Migration readiness result">
            <div><strong>{preflight.snapshot.status}</strong><span>{preflight.snapshot.input_checksum}</span></div>
            <p>Validation ID: {preflight.snapshot.preflight_id}</p>
            {preflight.snapshot.blockers.length > 0 ? <p>Blocking issues: {preflight.snapshot.blockers.join(", ")}</p> : null}
            {preflight.snapshot.warnings.length > 0 ? <p>Warnings: {preflight.snapshot.warnings.join(", ")}</p> : null}
            <p>{outputRootLabel}: {preflight.snapshot.resolved_output_root || pathValidation?.snapshot.resolved_output_root}</p>
            {artifactHref ? <a href={artifactHref}>Open validation evidence</a> : null}
          </section>
        ) : null}
        {validationStage ? <p role="status">Validating {validationStage}…</p> : null}
        {error ? <p className={styles.error} role="alert">{error}</p> : null}
      </section>
    </main>
  );
}
