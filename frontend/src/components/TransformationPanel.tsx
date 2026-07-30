"use client";

import { useMemo, useState } from "react";
import type { WorkflowEventDto } from "@/types/generated/api";
import { useTransformation } from "@/hooks/useTransformation";
import {
  cancelTransformation,
  decideTransformationGate,
  decideTransformationPrompt,
  restartTransformation,
} from "@/api/transformation";
import { LiveCommandLogViewer } from "@/components/LogViewer";

export function TransformationPanel({
  runId,
  workflowEvents,
}: {
  runId: string;
  workflowEvents: WorkflowEventDto[];
}) {
  const refreshKey = useMemo(
    () => workflowEvents.filter((event) =>
      event.event_type.startsWith("TRANSFORMATION_")
      || event.event_type.startsWith("COMMAND_")
      || /^G(?:0[7-9]|1[0-2])_/.test(event.event_type),
    ).at(-1)?.sequence ?? 0,
    [workflowEvents],
  );
  const { projection, status, refresh } = useTransformation(runId, refreshKey);
  const [actionError, setActionError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  if (status === "loading") return <section aria-label="Transformer status"><p>Loading Transformer status...</p></section>;
  if (status === "empty") return <section aria-label="Transformer status"><p>Transformer starts after accepted G06.</p></section>;
  if (status === "failed" || !projection) return <section aria-label="Transformer status"><p role="alert">Transformer status is unavailable. Refresh authoritative state.</p></section>;
  return <section aria-label="Transformer status" className="controlTowerPanel">
    <span className="controlTowerEyebrow">Durable Transformer</span>
    <h3>{projection.source_version ?? "source"} to {projection.target_version ?? "target"}</h3>
    <dl>
      <div><dt>Workflow</dt><dd>{projection.status} / {projection.current_node}</dd></div>
      <div><dt>Stage</dt><dd>{projection.stage_status}</dd></div>
      <div><dt>Gate</dt><dd>{projection.active_gate ?? "none"}</dd></div>
      <div><dt>Command</dt><dd>{projection.active_command_status ?? "none"}</dd></div>
      <div><dt>Checkpoint</dt><dd>{projection.checkpoint_kind ?? "not created"}</dd></div>
    </dl>
    {projection.workspace_fingerprint ? <p><code>{projection.workspace_fingerprint}</code></p> : null}
    {projection.active_command_id
      ? <LiveCommandLogViewer
          runId={runId}
          executionId={projection.active_command_id}
          executionStatus={projection.active_command_status ?? undefined}
        />
      : null}
    {projection.status === "waiting_prompt"
      && projection.active_prompt_id
      && projection.active_prompt_checksum ? <div>
        <h4>Angular CLI prompt</h4>
        <p>{projection.active_prompt_text}</p>
        {projection.active_prompt_explanation ? <>
          <p>{projection.active_prompt_explanation.summary}</p>
          <p>{projection.active_prompt_explanation.risk_note}</p>
          <small>Explanation: {projection.active_prompt_explanation.source}</small>
        </> : null}
        <div>
          {projection.active_prompt_options.map((option) =>
            <button
              key={option.option_id}
              type="button"
              disabled={submitting}
              onClick={() => void decidePrompt(option.option_id)}
            >
              {option.label}
            </button>
          )}
        </div>
      </div> : null}
    {projection.status === "waiting_gate"
      && projection.active_gate
      && projection.active_gate_package_checksum
      && projection.workspace_fingerprint ? <div>
        <button type="button" disabled={submitting} onClick={() => void decide("approve")}>
          Approve {projection.active_gate}
        </button>
        <button type="button" disabled={submitting} onClick={() => void decide("reject")}>
          Reject {projection.active_gate}
        </button>
      </div> : null}
    {!["completed", "cancelled", "failed"].includes(projection.status)
      ? <button type="button" disabled={submitting} onClick={() => void cancel()}>Cancel Transformer</button>
      : null}
    {projection.status === "blocked"
      ? <button type="button" disabled={submitting} onClick={() => void restart()}>Restart from checkpoint</button>
      : null}
    {actionError ? <p role="alert">{actionError}</p> : null}
    {projection.last_error_code ? <p role="alert">{projection.last_error_code}</p> : null}
  </section>;

  async function decide(decision: "approve" | "reject") {
    if (!projection?.active_gate || !projection.active_gate_package_checksum || !projection.workspace_fingerprint) return;
    setSubmitting(true);
    setActionError(null);
    const key = crypto.randomUUID();
    try {
      await decideTransformationGate(runId, projection.active_gate, {
        expected_state_version: projection.state_version,
        idempotency_key: key,
        package_checksum: projection.active_gate_package_checksum,
        workspace_fingerprint: projection.workspace_fingerprint,
        decision,
        correlation_id: key,
      });
      await refresh();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Gate decision failed.");
    } finally {
      setSubmitting(false);
    }
  }

  async function cancel() {
    if (!projection) return;
    setSubmitting(true);
    setActionError(null);
    const key = crypto.randomUUID();
    try {
      await cancelTransformation(runId, {
        expected_state_version: projection.state_version,
        idempotency_key: key,
        correlation_id: key,
      });
      await refresh();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Cancellation failed.");
    } finally {
      setSubmitting(false);
    }
  }

  async function decidePrompt(selectedOptionId: string) {
    if (!projection?.active_prompt_id || !projection.active_prompt_checksum) return;
    setSubmitting(true);
    setActionError(null);
    const key = crypto.randomUUID();
    try {
      await decideTransformationPrompt(runId, projection.active_prompt_id, {
        expected_state_version: projection.state_version,
        idempotency_key: key,
        prompt_checksum: projection.active_prompt_checksum,
        selected_option_id: selectedOptionId,
        correlation_id: key,
      });
      await refresh();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Prompt decision failed.");
    } finally {
      setSubmitting(false);
    }
  }

  async function restart() {
    if (!projection) return;
    setSubmitting(true);
    setActionError(null);
    const key = crypto.randomUUID();
    try {
      await restartTransformation(runId, {
        expected_state_version: projection.state_version,
        idempotency_key: key,
        correlation_id: key,
      });
      await refresh();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Restart failed.");
    } finally {
      setSubmitting(false);
    }
  }
}
