"use client";

import { useEffect, useMemo, useState } from "react";
import type { AuthoritativeRunStateDto, PlanningJobProjectionDto } from "@/types/generated/api";
import type { PlanCommand } from "@/types/planning";
import { usePlanProjection, type PlanProjectionStatus } from "@/hooks/usePlanProjection";
import { PlanningJobStatusCard } from "./PlanningJobStatusCard";
import styles from "./ControlTowerShell.module.css";
import panelStyles from "./MigrationPlanPanel.module.css";

const tabs = ["Commands", "Builder", "Validation", "Recovery", "Forbidden changes", "Artifacts"] as const;
type Tab = (typeof tabs)[number];

function statusMessage(status: PlanProjectionStatus, job?: PlanningJobProjectionDto | null) {
  if (status === "queued") return "The backend durably queued planning after G04 approval.";
  if (status === "resolving_feasibility") return "The backend is resolving feasibility inputs.";
  if (status === "waiting_g05") return "The feasibility package is waiting for G05 review.";
  if (status === "generating_plan") return "The backend is generating the migration plan.";
  if (status === "running_planning_review") return "The backend generated the plan and is running planning review.";
  if (status === "waiting_g06") return "The MigrationPlan and G06 package are ready for review.";
  if (status === "waiting_retry") return "The backend scheduled an automatic planning retry.";
  if (status === "completed_blocked") return "Planning completed with a blocking domain or review outcome.";
  if (status === "technical_failed") return "Planning ended with a terminal technical failure.";
  if (status === "empty") return job ? `No MigrationPlan is available while the planning job is ${job.status}.` : "No persisted MigrationPlan is available yet.";
  return null;
}

function CommandCard({ command }: { command: PlanCommand }) {
  return <article className={styles.previewPanel} aria-label={`Command ${command.command_id}`}>
    <div className={styles.previewHeader}><div><p className={styles.kicker}>Versioned command template</p><h4>{command.template_id} v{command.template_version}</h4></div><code>{command.command_id}</code></div>
    <dl className={styles.metadataGrid}>
      <div><dt>Executable</dt><dd><code>{command.executable}</code></dd></div>
      <div><dt>Arguments</dt><dd><code>{command.arguments.join(" ")}</code></dd></div>
      <div><dt>Workspace alias</dt><dd><code>{command.working_directory_alias}</code></dd></div>
      <div><dt>Timeout</dt><dd>{command.timeout_seconds}s</dd></div>
      <div><dt>Network</dt><dd><code>{command.network_profile}</code></dd></div>
      <div><dt>Conditional</dt><dd><code>{String(command.conditional)}</code></dd></div>
      <div><dt>Cancellation</dt><dd><code>{command.cancellation_policy}</code></dd></div>
      <div><dt>Runtime profile checksum</dt><dd><code>{command.runtime_profile_checksum ?? "not bound"}</code></dd></div>
    </dl>
    <details><summary>Parameter bindings</summary><pre className={panelStyles.codeBlock}>{JSON.stringify(command.parameter_bindings, null, 2)}</pre></details>
  </article>;
}

export function MigrationPlanPanel({ runId, initialState, connectionStatus, workflowEvents, refreshAuthoritativeState }: { runId: string; initialState: AuthoritativeRunStateDto; connectionStatus: string; artifacts?: unknown[]; workflowEvents: Array<{ event_type: string; sequence: number }>; refreshAuthoritativeState?: () => Promise<unknown> }) {
  const { plan, status, error } = usePlanProjection({ runId, stateVersion: initialState.state_version, planningJob: initialState.planning_job, workflowEvents, connectionStatus, refreshAuthoritativeState });
  const [tab, setTab] = useState<Tab>("Commands");
  useEffect(() => { if (status === "success") setTab("Commands"); }, [status, plan?.plan_checksum]);

  const stage = plan?.stage_plan;
  const route = useMemo(() => plan?.plan.route ?? [], [plan]);
  const progress = statusMessage(status, initialState.planning_job);
  const approvedForPreparation = initialState.status === "WAITING_STAGE_PREPARATION" || initialState.planning_job?.status === "completed";

  return <section className={styles.panel} aria-labelledby="migration-plan-title">
    <div className={styles.previewHeader}><div><p className={styles.kicker}>S2-F06</p><h2 id="migration-plan-title">Migration plan</h2><p className={styles.note}>Backend-owned plan projection; G05 starts generation automatically.</p></div><span className={styles.status}>{status}</span></div>
    {approvedForPreparation ? <p role="status"><strong>Plan approved for execution. Waiting for authoritative stage preparation.</strong></p> : null}
    <PlanningJobStatusCard job={initialState.planning_job} artifacts={initialState.artifacts} />
    {error ? <p role="alert">{error}</p> : null}
    {status === "authorization" ? <p role="alert">You are not authorized to inspect this run’s plan.</p> : null}
    {status === "blocked" ? <p role="alert">Plan evidence is blocked or failed integrity validation. Refresh the authoritative run and review the backend guidance.</p> : null}
    {status === "reconnecting" ? <p role="status">Connection interrupted. Reloading the authoritative plan after reconnect.</p> : null}
    {status === "loading" ? <p role="status">Loading authoritative MigrationPlan...</p> : null}
    {progress && !plan ? <p className={styles.note} role={["technical_failed", "completed_blocked"].includes(status) ? "alert" : "status"}>{progress}</p> : null}
    {plan && stage ? <>
      <div className={panelStyles.grid}>
        <div><span>Source</span><strong>{plan.plan.source_exact}</strong></div>
        <div><span>Target</span><strong>{plan.plan.target_family}</strong></div>
        <div><span>Plan version</span><strong>v{plan.plan.version}</strong></div>
        <div><span>Stage 1</span><strong>{stage.stage_id}</strong></div>
        <div><span>Evidence-set checksum</span><code>{stage.evidence_set_checksum ?? "not bound"}</code></div>
        <div><span>Physical workspace fingerprint</span><code>{stage.input_workspace_fingerprint ?? "not bound"}</code></div>
      </div>
      <h3>Major-stage route</h3><ol className={panelStyles.route}>{route.map((stageId, index) => <li className={panelStyles.routeItem} key={stageId}><span className={panelStyles.routeNumber}>{index + 1}</span><strong>{stageId}</strong><span className={styles.status}>{index === 0 ? "Stage 1 exact" : "Family route"}</span></li>)}</ol>
      <div className={panelStyles.tabs} role="tablist" aria-label="Migration plan details">{tabs.map((item) => <button type="button" role="tab" aria-selected={tab === item} key={item} onClick={() => setTab(item)}>{item}</button>)}</div>
      {tab === "Commands" ? <div role="tabpanel"><h3>Stage 1 structured commands</h3>{Object.entries(stage.commands).map(([name, commands]) => <section key={name}><h4>{name}</h4>{commands.map((command) => <CommandCard command={command} key={`${command.command_id}-${command.template_version}`} />)}</section>)}</div> : null}
      {tab === "Builder" ? <div role="tabpanel"><h3>Build-system decision</h3><div className={panelStyles.grid}><div><span>Builder</span><strong>{stage.build_system_decision.builder}</strong></div><div><span>Action</span><strong>{stage.build_system_decision.action}</strong></div><div><span>Decision checksum</span><code>{stage.build_system_decision.checksum}</code></div></div><p>{stage.build_system_decision.rationale}</p></div> : null}
      {tab === "Validation" ? <div role="tabpanel"><h3>Validation policy</h3><pre className={panelStyles.codeBlock}>{JSON.stringify(stage.validation_policy, null, 2)}</pre></div> : null}
      {tab === "Recovery" ? <div role="tabpanel"><h3>Recovery policy</h3><pre className={panelStyles.codeBlock}>{JSON.stringify(stage.recovery_policy, null, 2)}</pre><h3>Repair policy</h3><pre className={panelStyles.codeBlock}>{JSON.stringify(stage.repair_policy, null, 2)}</pre></div> : null}
      {tab === "Forbidden changes" ? <div role="tabpanel"><h3>Forbidden modernization</h3><ul className={styles.list}>{stage.forbidden_change_policy.actions.map((action) => <li key={action}><code>{action}</code></li>)}</ul></div> : null}
      {tab === "Artifacts" ? <div role="tabpanel"><h3>Immutable evidence</h3><ul className={styles.list}>{plan.artifact_ids.map((id) => <li className={panelStyles.artifact} key={id}><a href={plan.artifact_links[id] ?? `/api/v1/artifacts/${encodeURIComponent(id)}`} target="_blank" rel="noreferrer">{id}</a><code>{plan.artifact_checksums[id]}</code></li>)}</ul></div> : null}
    </> : null}
  </section>;
}
