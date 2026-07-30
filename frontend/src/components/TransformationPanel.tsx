"use client";

import { useMemo } from "react";
import type { WorkflowEventDto } from "@/types/generated/api";
import { useTransformation } from "@/hooks/useTransformation";

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
  const { projection, status } = useTransformation(runId, refreshKey);
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
    {projection.last_error_code ? <p role="alert">{projection.last_error_code}</p> : null}
  </section>;
}
