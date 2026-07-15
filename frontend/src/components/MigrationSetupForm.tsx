"use client";

import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { createMockMigration, validatePaths, validatePreflight } from "@/api/migrations";
import { getBackendBaseUrl } from "@/api/client";
import type { PathValidationResult, PreflightResultDto } from "@/types/generated/api";
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

function canStart(result: PreflightResultDto | null, currentKey: string, validatedKey: string | null): boolean {
  if (!result || currentKey !== validatedKey) return false;
  if (new Date(result.expires_at).getTime() <= Date.now()) return false;
  return result.status === "passed" || result.status === "passed_with_warnings";
}

export function MigrationSetupForm() {
  const router = useRouter();
  const [inputs, setInputs] = useState(initialInputs);
  const [preflight, setPreflight] = useState<PreflightResultDto | null>(null);
  const [pathValidation, setPathValidation] = useState<PathValidationResult | null>(null);
  const [validatedKey, setValidatedKey] = useState<string | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const currentKey = useMemo(() => inputKey(inputs), [inputs]);
  const startEnabled = canStart(preflight, currentKey, validatedKey);

  async function runPreflight() {
    setIsValidating(true);
    setError(null);
    try {
      const pathResult = await validatePaths({
        source_path: inputs.sourcePath,
        target_parent_path: inputs.targetParentPath,
        idempotency_key: "path-ui-" + Date.now(),
        actor: "control-tower",
      });
      setPathValidation(pathResult);
      if (pathResult.snapshot.status === "blocked") {
        setPreflight(null);
        setValidatedKey(null);
        return;
      }
      const result = await validatePreflight({
        source_path: inputs.sourcePath,
        target_output_path: pathResult.snapshot.resolved_output_root,
        target_angular_family: inputs.targetAngularFamily,
        migration_mode: inputs.migrationMode,
        auto_approval_enabled: false
      });
      setPreflight(result);
      setValidatedKey(currentKey);
    } catch {
      setError("Preflight request failed.");
      setPreflight(null);
      setValidatedKey(null);
    } finally {
      setIsValidating(false);
    }
  }

  async function startMigration(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!preflight || !startEnabled) return;
    setIsStarting(true);
    setError(null);
    try {
      const run = await createMockMigration({ preflight_checksum: preflight.checksum });
      router.push(`/migrations/${run.run_id}`);
    } catch {
      setError("Start request failed.");
    } finally {
      setIsStarting(false);
    }
  }

  const artifactHref = preflight?.artifact ? `${getBackendBaseUrl()}/api/v1/artifacts/${preflight.artifact.artifact_id}` : null;

  return (
    <main className={styles.page}>
      <section className={styles.panel}>
        <p className={styles.kicker}>Control Tower</p>
        <h1>Prepare external migration</h1><p>The original application remains unchanged. All snapshots, sandboxes, artifacts, logs, reports, and migrated output are created inside the generated external migration folder.</p>
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
        {pathValidation ? (
          <section className={styles.result} aria-label="Path validation result">
            <div><strong>{pathValidation.snapshot.status}</strong><span>{pathValidation.snapshot.checksum}</span></div>
            {pathValidation.snapshot.blockers.length > 0 ? <p>Blockers: {pathValidation.snapshot.blockers.join(", ")}</p> : null}
            {pathValidation.snapshot.warnings.length > 0 ? <p>Warnings: {pathValidation.snapshot.warnings.join(", ")}</p> : null}
            <p>Generated output: {pathValidation.snapshot.resolved_output_root}</p>
            <p>Future migrated app: {pathValidation.snapshot.resolved_output_root}\\migrated-app</p>
            <p>Migration workspace: {pathValidation.snapshot.resolved_output_root}\\.migration-factory</p>
            {pathValidation.snapshot.source_fingerprint ? <p>Source fingerprint: {pathValidation.snapshot.source_fingerprint}</p> : null}
          </section>
        ) : null}
        {preflight ? (
          <section className={styles.result} aria-label="Preflight result">
            <div><strong>{preflight.status}</strong><span>{preflight.checksum}</span></div>
            {preflight.blockers.length > 0 ? <p>Blockers: {preflight.blockers.join(", ")}</p> : null}
            {preflight.warnings.length > 0 ? <p>Warnings: {preflight.warnings.join(", ")}</p> : null}
            {artifactHref ? <a href={artifactHref}>Open preflight artifact</a> : null}
          </section>
        ) : null}
        {error ? <p className={styles.error}>{error}</p> : null}
      </section>
    </main>
  );
}
