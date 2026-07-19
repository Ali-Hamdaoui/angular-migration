"use client";

import { useAcceptanceChecklist } from "@/hooks/useAcceptanceChecklist";
import type {
  HarnessFixtureType,
  HarnessStatusDto,
} from "@/types/generated/api";
import styles from "./AcceptanceChecklist.module.css";

const FIXTURE_LABELS: Record<string, string> = {
  angular_180x: "Angular 18.0.x",
  angular_182x: "Angular 18.2.x",
  passable: "Passing Build",
  compiler_error: "Compiler Error",
  dependency_conflict: "Dependency Conflict",
  environment_blocker: "Environment Blocker",
  cancellable: "Cancellable",
};

const FIXTURE_TYPES: HarnessFixtureType[] = [
  "angular_180x",
  "angular_182x",
  "passable",
  "compiler_error",
  "dependency_conflict",
  "environment_blocker",
  "cancellable",
];

interface AcceptanceChecklistProps {
  initialStatus: HarnessStatusDto | null;
  runId?: string | null;
}

export function AcceptanceChecklist({
  initialStatus,
  runId = null,
}: AcceptanceChecklistProps) {
  const {
    status,
    suiteStatus,
    runDetails,
    error,
    start,
    evaluate,
    evidence,
  } = useAcceptanceChecklist(initialStatus, runId);

  const connectionLabel = statusLabel(status);
  const connectionClass = styles[`connectionBar_${status}`] ?? "";

  const fixtures = suiteStatus?.fixtures ?? [];
  const fixtureMap = new Map(fixtures.map((f) => [f.fixture_type, f]));

  return (
    <div className={styles.shell}>
      <div className={styles.header}>
        <div>
          <h1>Operator Acceptance Checklist</h1>
          <p>Angular Acceptance Harness — Phase A</p>
        </div>
        <div className={`${styles.connectionBar} ${connectionClass}`} role="status" aria-live="polite">
          {connectionLabel}
        </div>
      </div>

      {/* Dimension grid */}
      <div className={styles.dimensionGrid}>
        <div className={styles.dimensionCard}>
          <dt>Overall Status</dt>
          <dd>{suiteStatus?.overall_status ?? "—"}</dd>
        </div>
        <div className={styles.dimensionCard}>
          <dt>Fixtures</dt>
          <dd>{fixtures.length}</dd>
        </div>
        <div className={styles.dimensionCard}>
          <dt>Errors</dt>
          <dd>{suiteStatus?.errors?.length ?? 0}</dd>
        </div>
        <div className={styles.dimensionCard}>
          <dt>Evidence Artifacts</dt>
          <dd>{evidence.length}</dd>
        </div>
      </div>

      {/* Error banner */}
      {error && <div className={styles.errorBanner}>{error}</div>}

      {/* Scenario grid */}
      {fixtures.length === 0 && status !== "loading" ? (
        <div className={styles.emptyState}>
          No fixtures have been evaluated yet. Select a scenario to begin.
        </div>
      ) : (
        <div className={styles.scenarioGrid}>
          {FIXTURE_TYPES.map((fixtureType) => {
            const result = fixtureMap.get(fixtureType);
            const outcome = result?.outcome ?? "PENDING";
            const cardClass =
              outcome === "pass" || outcome === "SUCCEEDED"
                ? styles.scenarioPass
                : outcome === "fail" || outcome === "FAILED"
                  ? styles.scenarioFail
                  : outcome === "BLOCKED"
                    ? styles.scenarioBlocked
                    : styles.scenarioPending;
            const statusClass =
              outcome === "pass" || outcome === "SUCCEEDED"
                ? styles.scenarioStatusPass
                : outcome === "fail" || outcome === "FAILED"
                  ? styles.scenarioStatusFail
                  : styles.scenarioStatusPending;

            return (
              <div
                key={fixtureType}
                className={`${styles.scenarioCard} ${cardClass}`}
                aria-label={`Scenario: ${FIXTURE_LABELS[fixtureType] ?? fixtureType}`}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span className={styles.scenarioTitle}>
                    {FIXTURE_LABELS[fixtureType] ?? fixtureType}
                  </span>
                  <span className={`${styles.scenarioStatus} ${statusClass}`}>
                    {outcome}
                  </span>
                </div>

                {result && (
                  <dl className={styles.metaGrid}>
                    <dt>ID</dt>
                    <dd>{result.fixture_id}</dd>
                    <dt>State</dt>
                    <dd>v{result.state_version}</dd>
                    {result.fixture_root && (
                      <>
                        <dt>Root</dt>
                        <dd>{result.fixture_root}</dd>
                      </>
                    )}
                  </dl>
                )}

                {result && result.evidence_refs.length > 0 && (
                  <div>
                    <strong style={{ fontSize: "0.75rem", color: "#8892a4" }}>
                      Evidence
                    </strong>
                    <ul className={styles.evidenceList}>
                      {result.evidence_refs.map((ref) => (
                        <li key={ref.artifact_id} className={styles.evidenceItem}>
                          <code>{ref.artifact_type}</code>
                          <span>{ref.relative_path}</span>
                          <span style={{ color: "#5a8cff", fontSize: "0.65rem" }}>
                            {ref.checksum.slice(0, 16)}…
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                <div className={styles.actionBar}>
                  <button
                    className={styles.button}
                    disabled={status !== "idle" && status !== "polling"}
                    onClick={() => start(fixtureType)}
                    aria-label={`Start ${FIXTURE_LABELS[fixtureType] ?? fixtureType}`}
                  >
                    Start
                  </button>
                  <button
                    className={`${styles.button} ${styles.buttonOutline}`}
                    disabled={!result || (status !== "idle" && status !== "polling")}
                    onClick={() => result && evaluate(result.fixture_id)}
                    aria-label={`Evaluate ${FIXTURE_LABELS[fixtureType] ?? fixtureType}`}
                  >
                    Evaluate
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Run details */}
      {runDetails && (
        <div className={styles.dimensionGrid}>
          <div className={styles.dimensionCard}>
            <dt>Run ID</dt>
            <dd style={{ fontSize: "0.8rem" }}>{runDetails.run_id}</dd>
          </div>
          <div className={styles.dimensionCard}>
            <dt>Suite Status</dt>
            <dd>{runDetails.overall_status}</dd>
          </div>
          <div className={styles.dimensionCard}>
            <dt>Passed / Failed</dt>
            <dd>{runDetails.passed} / {runDetails.failed}</dd>
          </div>
          {runDetails.started_at && (
            <div className={styles.dimensionCard}>
              <dt>Started</dt>
              <dd style={{ fontSize: "0.8rem" }}>
                {new Date(runDetails.started_at).toLocaleString()}
              </dd>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function statusLabel(status: string): string {
  switch (status) {
    case "loading":
      return "Connecting to backend…";
    case "idle":
      return "All systems nominal";
    case "polling":
      return "Checking backend…";
    case "stale":
      return "State is stale — refresh";
    case "backend-failure":
      return "Backend unreachable — retrying";
    case "reconnect-required":
      return "Reconnection needed";
    default:
      return status;
  }
}
