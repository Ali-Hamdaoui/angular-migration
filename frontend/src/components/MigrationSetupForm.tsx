"use client";

import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { validatePreflight } from "@/api/migrations";
import type { PreflightRequestDto, PreflightResultDto } from "@/types/generated/api";
import styles from "./MigrationSetupForm.module.css";

type SetupInputs = {
  source_path: string;
  target_output_path: string;
  target_angular_family: string;
  migration_mode: string;
  auto_approval_enabled: boolean;
};

const initialInputs: SetupInputs = {
  source_path: "",
  target_output_path: "",
  target_angular_family: "21.x",
  migration_mode: "strict-functional-parity",
  auto_approval_enabled: false
};

function toRequest(inputs: SetupInputs): PreflightRequestDto {
  return { ...inputs };
}

function inputsKey(inputs: SetupInputs): string {
  return JSON.stringify(inputs);
}

export function MigrationSetupForm() {
  const router = useRouter();
  const [inputs, setInputs] = useState<SetupInputs>(initialInputs);
  const [validatedKey, setValidatedKey] = useState<string | null>(null);
  const [preflight, setPreflight] = useState<PreflightResultDto | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const currentKey = useMemo(() => inputsKey(inputs), [inputs]);
  const isExpired = preflight ? Date.parse(preflight.expires_at) <= Date.now() : false;
  const isCurrent = preflight !== null && validatedKey === currentKey && !isExpired;
  const canStart = isCurrent && (preflight.status === "passed" || preflight.status === "passed_with_warnings");
  const staleMessage = preflight && !isCurrent ? "Inputs changed or the preflight expired. Validate again before starting." : null;

  async function handleValidate() {
    setIsValidating(true);
    setError(null);
    try {
      const result = await validatePreflight(toRequest(inputs));
      setPreflight(result);
      setValidatedKey(currentKey);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Preflight validation failed.");
    } finally {
      setIsValidating(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (canStart) {
      router.push("/migrations/mock-run-angular-18-to-21");
    }
  }

  return (
    <main className={styles.page}>
      <section className={styles.panel}>
        <p className={styles.kicker}>Control Tower</p>
        <h1>Start mock migration</h1>
        <p>This form validates setup intent before Sprint 0 mock run creation.</p>
        <form onSubmit={handleSubmit}>
          <label>
            Source path
            <input
              name="sourcePath"
              required
              placeholder="C:\\projects\\angular-18-app"
              value={inputs.source_path}
              onChange={(event) => setInputs({ ...inputs, source_path: event.target.value })}
            />
          </label>
          <label>
            Target output path
            <input
              name="targetOutputPath"
              required
              placeholder="C:\\migration-output"
              value={inputs.target_output_path}
              onChange={(event) => setInputs({ ...inputs, target_output_path: event.target.value })}
            />
          </label>
          <label>
            Target Angular family
            <select
              name="targetAngularFamily"
              value={inputs.target_angular_family}
              onChange={(event) => setInputs({ ...inputs, target_angular_family: event.target.value })}
            >
              <option>21.x</option>
            </select>
          </label>
          <label>
            Migration mode
            <select
              name="migrationMode"
              value={inputs.migration_mode}
              onChange={(event) => setInputs({ ...inputs, migration_mode: event.target.value })}
            >
              <option value="strict-functional-parity">Strict functional parity</option>
            </select>
          </label>
          <label className={styles.checkbox}>
            <input
              name="autoApprovalEnabled"
              type="checkbox"
              checked={inputs.auto_approval_enabled}
              onChange={(event) => setInputs({ ...inputs, auto_approval_enabled: event.target.checked })}
            />
            Enable auto-approval where future backend policy allows
          </label>
          <div className={styles.actions}>
            <button type="button" onClick={handleValidate} disabled={isValidating || !inputs.source_path || !inputs.target_output_path}>
              {isValidating ? "Validating" : "Validate setup"}
            </button>
            <button type="submit" disabled={!canStart}>Start Mock Migration</button>
          </div>
        </form>
        {error ? <p className={styles.error}>{error}</p> : null}
        {staleMessage ? <p className={styles.warning}>{staleMessage}</p> : null}
        {preflight ? (
          <section className={styles.preflight} aria-label="Preflight result">
            <div><strong>Status</strong><span>{preflight.status.replaceAll("_", " ")}</span></div>
            <div><strong>Checksum</strong><span>{preflight.input_checksum}</span></div>
            {preflight.artifact ? <div><strong>Artifact</strong><span>{preflight.artifact.relative_path}</span></div> : null}
            <ul>
              {preflight.findings.map((finding) => <li key={finding.code}>{finding.code}: {finding.message}</li>)}
            </ul>
          </section>
        ) : null}
      </section>
    </main>
  );
}
