"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { ArtifactRefDto, WorkflowEventDto } from "@/types/generated/api";
import { ApiClientError } from "@/api/client";
import { useTransformation } from "@/hooks/useTransformation";
import { TRANSFORMATION_EVENT_TYPES } from "@/hooks/useAuthoritativeRun";
import {
  cancelTransformation,
  decideTransformationGate,
  decideTransformationPrompt,
  restartTransformation,
} from "@/api/transformation";
import {
  LogsAndDiagnostics,
  RepairEvidence,
  SealAndRoute,
  StageSummary,
  TransformationEvidence,
  ValidationEvidence,
  WorkerStatus,
} from "./TransformationSections";
import styles from "./TransformationPanel.module.css";

type Props = {
  runId: string;
  workflowEvents: WorkflowEventDto[];
  artifacts: ArtifactRefDto[];
  authoritativeStatus: string;
  authoritativePhase: string;
  authoritativeStateVersion: number;
  refreshAuthoritativeState: () => Promise<void> | void;
  onActionRequiredChange?: (required: boolean) => void;
};

const terminalStatuses = new Set(["completed", "cancelled", "failed"]);
const transformerEvents = new Set<string>(TRANSFORMATION_EVENT_TYPES);

function conflictMessage(error: ApiClientError) {
  let code = "STALE_STATE";
  try {
    const body = JSON.parse(error.responseBody ?? "{}") as {
      error?: { code?: string };
      error_code?: string;
    };
    code = body.error?.code ?? body.error_code ?? code;
  } catch {
    // The status code is sufficient; provider text is never rendered.
  }
  return `Authoritative state changed (${code}). Latest state has been reloaded.`;
}

export function TransformationPanel({
  runId,
  workflowEvents,
  artifacts,
  authoritativeStatus,
  authoritativePhase,
  authoritativeStateVersion,
  refreshAuthoritativeState,
  onActionRequiredChange,
}: Props) {
  const refreshKey = useMemo(
    () => workflowEvents.filter((event) =>
      transformerEvents.has(event.event_type) || event.event_type.startsWith("COMMAND_"),
    ).at(-1)?.sequence ?? 0,
    [workflowEvents],
  );
  const { projection, status, refresh } = useTransformation(runId, refreshKey);
  const [actionError, setActionError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const submittingRef = useRef(false);
  const actionRequired = projection?.status === "waiting_prompt"
    || (projection?.status === "waiting_gate" && /^G(?:0[7-9]|1[0-2])$/.test(projection.active_gate ?? ""));

  useEffect(() => {
    if (status !== "loading") onActionRequiredChange?.(Boolean(actionRequired));
  }, [actionRequired, onActionRequiredChange, status]);

  if (status === "loading") {
    return <section className={styles.empty} aria-label="Transformer status" role="status">
      <p>Loading authoritative Transformer state…</p>
    </section>;
  }
  if (status === "empty") {
    const g06 = workflowEvents.filter((event) => event.event_type.startsWith("G06_")).at(-1);
    return <section className={styles.empty} aria-label="Transformer status">
      <span className={styles.eyebrow}>Transformation prerequisite</span>
      <h3>Transformer continuation has not been created</h3>
      <p>Accept G06 in Planning to create the durable Transformer continuation. This screen remains available while Planning is pending, rejected, stale, or unavailable.</p>
      <dl className={styles.metadata}>
        <div><dt>Run status</dt><dd>{authoritativeStatus}</dd></div>
        <div><dt>Run phase</dt><dd>{authoritativePhase}</dd></div>
        <div><dt>Run state version</dt><dd>{authoritativeStateVersion}</dd></div>
        <div><dt>Latest G06 evidence</dt><dd>{g06?.event_type ?? "none"}</dd></div>
      </dl>
    </section>;
  }
  if (status === "failed" || !projection) {
    return <section className={styles.empty} aria-label="Transformer status">
      <h3>Transformer state unavailable</h3>
      <p role="alert">The backend projection could not be loaded. The frontend has not inferred a workflow result.</p>
      <button type="button" onClick={() => void refresh()}>Retry Transformer state</button>
    </section>;
  }

  const current = projection;
  const shared = { projection: current, workflowEvents, artifacts };
  return <div className={styles.screen} aria-label="Transformer status">
    <section className={styles.hero}>
      <div>
        <span className={styles.eyebrow}>Durable Transformer / backend truth</span>
        <h3>{projection.source_version ?? "source"} → {projection.target_version ?? "target"}</h3>
        <p>Current step: <code>{projection.current_node}</code></p>
      </div>
      <span className={styles.status}>{projection.status}</span>
    </section>

    {actionError ? <p className={styles.alert} role="alert">{actionError}</p> : null}

    <div className={styles.grid}>
      <StageSummary projection={projection} workflowEvents={workflowEvents} />
      <WorkerStatus projection={projection} />

      <section className={`${styles.card} ${styles.cardWide}`} aria-labelledby="transform-current-action">
        <span className={styles.eyebrow}>03 / Current action or gate</span>
        <div className={styles.cardHeader}>
          <div>
            <h3 id="transform-current-action">
              {projection.active_gate ? `${projection.active_gate} approval` : projection.status === "waiting_prompt" ? "CLI prompt decision" : "No human action requested"}
            </h3>
            <p className={styles.note}>Backend state: {projection.status} / {projection.current_node}</p>
          </div>
        </div>
        {projection.status === "waiting_gate"
          && projection.active_gate
          && projection.active_gate_package_checksum
          && projection.workspace_fingerprint
          ? <div className={styles.actions}>
              <button type="button" disabled={submitting} onClick={() => void decideGate("approve")}>
                Approve {projection.active_gate}
              </button>
              <button type="button" disabled={submitting} onClick={() => void decideGate("reject")}>
                Reject {projection.active_gate}
              </button>
            </div>
          : projection.status === "waiting_gate"
            ? <p className={styles.alert} role="alert">The active gate lacks the backend package checksum or workspace fingerprint required for a safe decision.</p>
            : null}
      </section>

      <LogsAndDiagnostics projection={projection} workflowEvents={workflowEvents} />

      <section className={`${styles.card} ${styles.cardWide} ${projection.status === "waiting_prompt" ? styles.prompt : ""}`} aria-labelledby="transform-prompt">
        <span className={styles.eyebrow}>05 / Prompt decision and reconstruction</span>
        <h3 id="transform-prompt">Angular CLI prompt</h3>
        {projection.status === "waiting_prompt"
          && projection.active_prompt_id
          && projection.active_prompt_checksum
          ? <>
              <p className={styles.promptText}>{projection.active_prompt_text ?? "Prompt text unavailable"}</p>
              {projection.active_prompt_explanation ? <>
                <p className={styles.promptText}>{projection.active_prompt_explanation.summary}</p>
                <ul className={styles.optionEffects}>
                  {projection.active_prompt_explanation.option_effects.map((effect) => <li key={effect}>{effect}</li>)}
                </ul>
                <p className={styles.promptText}>{projection.active_prompt_explanation.risk_note}</p>
                <small>Explanation status: {projection.active_prompt_explanation.source}</small>
              </> : <p className={styles.note}>Azure explanation is not available yet.</p>}
              <div className={styles.actions}>
                {projection.active_prompt_options.map((option) => <button
                  key={option.option_id}
                  type="button"
                  disabled={submitting}
                  onClick={() => void decidePrompt(option.option_id)}
                >
                  {option.label}
                </button>)}
              </div>
            </>
          : <p className={styles.note}>No unresolved CLI prompt is projected. Reconstruction and deterministic retry status appear in the current step and workflow diagnostics.</p>}
      </section>

      <TransformationEvidence {...shared} />
      <ValidationEvidence {...shared} />
      <RepairEvidence {...shared} />
      <SealAndRoute {...shared} />
    </div>

    <div className={styles.actions}>
      {!terminalStatuses.has(projection.status)
        ? <button className={styles.danger} type="button" disabled={submitting} onClick={() => void cancel()}>
            Cancel Transformer
          </button>
        : null}
      {["blocked", "failed", "waiting_retry"].includes(projection.status)
        ? <button type="button" disabled={submitting} onClick={() => void restart()}>
            Restart from durable state
          </button>
        : null}
    </div>
  </div>;

  async function refreshAll() {
    await Promise.all([refresh(), refreshAuthoritativeState()]);
  }

  async function mutate(action: (key: string) => Promise<unknown>, fallback: string) {
    if (submittingRef.current) return;
    submittingRef.current = true;
    setSubmitting(true);
    setActionError(null);
    const key = crypto.randomUUID();
    try {
      await action(key);
      await refreshAll();
    } catch (error) {
      if (error instanceof ApiClientError && error.status === 409) {
        await Promise.allSettled([refresh(), Promise.resolve(refreshAuthoritativeState())]);
        setActionError(conflictMessage(error));
      } else {
        setActionError(error instanceof Error ? error.message : fallback);
      }
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  }

  function decideGate(decision: "approve" | "reject") {
    if (!current.active_gate || !current.active_gate_package_checksum || !current.workspace_fingerprint) return;
    return mutate((key) => decideTransformationGate(runId, current.active_gate!, {
      expected_state_version: current.state_version,
      idempotency_key: key,
      package_checksum: current.active_gate_package_checksum!,
      workspace_fingerprint: current.workspace_fingerprint!,
      decision,
      correlation_id: key,
    }), "Gate decision failed.");
  }

  function decidePrompt(selectedOptionId: string) {
    if (!current.active_prompt_id || !current.active_prompt_checksum) return;
    return mutate((key) => decideTransformationPrompt(runId, current.active_prompt_id!, {
      expected_state_version: current.state_version,
      idempotency_key: key,
      prompt_checksum: current.active_prompt_checksum!,
      selected_option_id: selectedOptionId,
      correlation_id: key,
    }), "Prompt decision failed.");
  }

  function cancel() {
    return mutate((key) => cancelTransformation(runId, {
      expected_state_version: current.state_version,
      idempotency_key: key,
      correlation_id: key,
    }), "Cancellation failed.");
  }

  function restart() {
    return mutate((key) => restartTransformation(runId, {
      expected_state_version: current.state_version,
      idempotency_key: key,
      correlation_id: key,
    }), "Restart failed.");
  }
}
