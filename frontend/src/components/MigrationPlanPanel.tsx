"use client";

import { useEffect, useMemo, useState } from "react";
import type { AuthoritativeRunStateDto } from "@/types/generated/api";
import { usePlanProjection } from "@/hooks/usePlanProjection";
import styles from "./ControlTowerShell.module.css";
import panelStyles from "./MigrationPlanPanel.module.css";

const tabs = ["Commands", "Builder", "Validation", "Recovery", "Forbidden changes", "Artifacts"] as const;
type Tab = (typeof tabs)[number];

export function MigrationPlanPanel({ runId, initialState, connectionStatus, workflowEvents, refreshAuthoritativeState }: { runId: string; initialState: AuthoritativeRunStateDto; connectionStatus: string; artifacts?: unknown[]; workflowEvents: Array<{ event_type: string; sequence: number }>; refreshAuthoritativeState?: () => Promise<unknown> }) {
  const { plan, status, error } = usePlanProjection({ runId, stateVersion: initialState.state_version, planningJob: initialState.planning_job, workflowEvents, connectionStatus, refreshAuthoritativeState });
  const [tab, setTab] = useState<Tab>("Commands");
  const statusLabel = status === "reconnecting" ? "Reconnecting; refreshing authoritative plan..." : status === "queued" ? "Planning queued" : status === "resolving_feasibility" ? "Resolving feasibility" : status === "waiting_g05" ? "Waiting for G05 approval" : status === "generating_plan" ? "Generating migration plan" : status === "running_planning_review" ? "Reviewing migration plan" : status === "waiting_retry" ? "Planning retry scheduled" : status === "technical_failed" ? "Planning failed" : status === "completed_blocked" ? "Feasibility blocked" : status === "waiting_g06" ? "Waiting for G06 approval" : status === "completed" ? "Planning approved" : status === "running" ? "Generating plan..." : status;

  useEffect(() => { if (status === "success") setTab("Commands"); }, [status, plan?.plan_checksum]);

  const stage = plan?.stage_plan;
  const route = useMemo(() => plan?.plan.route ?? [], [plan]);
  return <section className={styles.panel} aria-labelledby="migration-plan-title">
    <div className={styles.previewHeader}><div><p className={styles.kicker}>Migration plan · Gate G06</p><h2 id="migration-plan-title">Migration plan</h2><p className={styles.note}>Backend-owned plan projection; no local workflow advancement.</p></div><span className={styles.status}>{statusLabel}</span></div>
    {error ? <p role="alert">{error}</p> : null}
    {status === "authorization" ? <p role="alert">You are not authorized to inspect this run’s plan.</p> : null}
    {status === "blocked" ? <p role="alert">Plan evidence is blocked or failed integrity validation. Refresh the authoritative run and review the backend guidance.</p> : null}
    {status === "stale" ? <p role="alert">The plan request used a stale state version. The authoritative snapshot was reloaded; review prerequisites before retrying.</p> : null}
    {status === "loading" ? <p role="status">Loading authoritative MigrationPlan...</p> : null}
    {status === "empty" ? <p className={styles.note}>No persisted migration plan is available yet.</p> : null}
     {initialState.planning_job && ["waiting_retry", "technical_failed"].includes(status) ? <div role="alert"><p>{initialState.planning_job.last_error_code ?? "PLANNING_FAILED"}{initialState.planning_job.last_error_stage ? " at " + initialState.planning_job.last_error_stage : ""}</p><p>{initialState.planning_job.last_error_message ?? "The planning continuation could not complete."}</p><p>Attempt {initialState.planning_job.attempt}{initialState.planning_job.retryable ? ` of ${initialState.planning_job.max_attempts}` : " (terminal)"}{initialState.planning_job.next_attempt_at ? "; next attempt " + initialState.planning_job.next_attempt_at : ""}{initialState.planning_job.correlation_id ? "; correlation " + initialState.planning_job.correlation_id : ""}</p></div> : null}
    {plan && stage ? <>
      <div className={panelStyles.grid}><div><span>Source</span><strong>{plan.plan.source_exact} ({plan.plan.source_family})</strong></div><div><span>Target</span><strong>{plan.plan.target_family}</strong></div><div><span>Plan version</span><strong>{plan.plan.version}</strong></div><div><span>Plan checksum</span><code>{plan.plan_checksum}</code></div></div>
      <h3>Major-stage route</h3><ol className={panelStyles.route}>{route.map((stageId, index) => <li className={panelStyles.routeItem} key={stageId}><span className={panelStyles.routeNumber}>{index + 1}</span><strong>{stageId}</strong><span className={styles.status}>{index === 0 ? "Stage 1 exact" : "Family route"}</span></li>)}</ol>
      <div className={panelStyles.tabs} role="tablist" aria-label="Migration plan details">{tabs.map((item) => <button type="button" role="tab" aria-selected={tab === item} key={item} onClick={() => setTab(item)}>{item}</button>)}</div>
      {tab === "Commands" ? <div role="tabpanel"><h3>Stage 1 structured commands</h3>{Object.entries(stage.commands).map(([name, commands]) => <div key={name}><strong>{name}</strong>{commands.map((command) => <pre className={panelStyles.codeBlock} key={command.command_id}>{JSON.stringify(command, null, 2)}</pre>)}</div>)}</div> : null}
      {tab === "Builder" ? <div role="tabpanel"><h3>Build-system decision</h3><div className={panelStyles.grid}><div><span>Builder</span><strong>{stage.build_system_decision.builder}</strong></div><div><span>Action</span><strong>{stage.build_system_decision.action}</strong></div><div><span>Decision checksum</span><code>{stage.build_system_decision.checksum}</code></div></div><p>{stage.build_system_decision.rationale}</p></div> : null}
      {tab === "Validation" ? <div role="tabpanel"><h3>Validation policy</h3><pre className={panelStyles.codeBlock}>{JSON.stringify(stage.validation_policy, null, 2)}</pre></div> : null}
      {tab === "Recovery" ? <div role="tabpanel"><h3>Recovery policy</h3><pre className={panelStyles.codeBlock}>{JSON.stringify(stage.recovery_policy, null, 2)}</pre><h3>Repair policy</h3><pre className={panelStyles.codeBlock}>{JSON.stringify(stage.repair_policy, null, 2)}</pre></div> : null}
      {tab === "Forbidden changes" ? <div role="tabpanel"><h3>Forbidden modernization</h3><ul className={styles.list}>{stage.forbidden_change_policy.actions.map((action) => <li key={action}><code>{action}</code></li>)}</ul></div> : null}
      {tab === "Artifacts" ? <div role="tabpanel"><h3>Immutable evidence</h3><ul className={styles.list}>{plan.artifact_ids.map((id) => <li className={panelStyles.artifact} key={id}><a href={plan.artifact_links[id] ?? `/api/v1/artifacts/${encodeURIComponent(id)}`} target="_blank" rel="noreferrer">{id}</a><code>{plan.artifact_checksums[id]}</code></li>)}</ul></div> : null}
    </> : null}
  </section>;
}
