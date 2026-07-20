"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiClientError } from "@/api/client";
import { listCommandTemplates, validateCommandPolicy } from "@/api/commands";
import { getStagePlan } from "@/api/plans";
import { CommandExecutionPanel } from "./CommandExecutionPanel";
import type {
  AuthoritativeRunStateDto,
  CommandPolicyValidateRequestDto,
  CommandPolicyValidateResponseDto,
  CommandTemplateDto,
  CommandTemplateListDto,
  WorkflowEventDto,
} from "@/types/generated/api";
import type { PlanResponse } from "@/types/planning";
import styles from "./ControlTowerShell.module.css";

type InspectorStatus = "loading" | "ready" | "validating" | "accepted" | "rejected" | "stale" | "conflict" | "unavailable" | "reconnecting";

interface CommandPolicyInspectorProps {
  runId: string | null;
  runState?: AuthoritativeRunStateDto;
  stageId?: string | null;
  stateVersion?: number;
  connectionStatus?: string;
  refreshAuthoritativeState?: () => Promise<unknown>;
  workflowEvents?: WorkflowEventDto[];
}

function errorDetails(error: unknown) {
  if (!(error instanceof ApiClientError)) return { code: "BACKEND_UNAVAILABLE", correlationId: null, message: "The backend could not be reached." };
  try {
    const payload = JSON.parse(error.responseBody ?? "{}") as { error_code?: string; message?: string; correlation_id?: string; detail?: { code?: string; message?: string; correlation_id?: string } };
    const detail = payload.detail ?? {};
    return { code: payload.error_code ?? detail.code ?? (error.status === 409 ? "CONFLICT" : "BACKEND_UNAVAILABLE"), correlationId: payload.correlation_id ?? detail.correlation_id ?? null, message: payload.message ?? detail.message ?? error.message };
  } catch {
    return { code: error.status === 409 ? "CONFLICT" : "BACKEND_UNAVAILABLE", correlationId: null, message: error.message };
  }
}

function newCorrelationId() {
  return typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `corr-${Math.random().toString(36).slice(2)}`;
}

export function CommandPolicyInspector({ runId, runState, stageId, stateVersion, connectionStatus, refreshAuthoritativeState, workflowEvents }: CommandPolicyInspectorProps) {
  const [templates, setTemplates] = useState<CommandTemplateListDto | null>(null);
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [status, setStatus] = useState<InspectorStatus>("loading");
  const [message, setMessage] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [correlationId, setCorrelationId] = useState<string | null>(null);
  const [selectedTemplate, setSelectedTemplate] = useState<CommandTemplateDto | null>(null);
  const [validationResult, setValidationResult] = useState<CommandPolicyValidateResponseDto | null>(null);
  const [lastRequest, setLastRequest] = useState<CommandPolicyValidateRequestDto | null>(null);
  const attemptKey = useRef<string | null>(null);

  const currentStageId = stageId ?? runState?.workflow_events.slice().reverse().find((event) => event.stage_id)?.stage_id ?? null;
  const currentVersion = runState?.state_version ?? stateVersion ?? 1;
  const workspaceAliases = useMemo(() => runState?.workspace_aliases ?? {}, [runState?.workspace_aliases]);

  const refresh = useCallback(async () => {
    if (!runId) {
      setStatus("ready");
      return;
    }
    setStatus(connectionStatus === "reconnecting" || connectionStatus === "recovering" ? "reconnecting" : "loading");
    setMessage(null);
    try {
      const [templateList, stagePlan] = await Promise.all([
        listCommandTemplates(),
        currentStageId ? getStagePlan(runId, currentStageId) : Promise.resolve(null),
      ]);
      setTemplates(templateList);
      setPlan(stagePlan);
      setStatus("ready");
    } catch (reason: unknown) {
      const details = errorDetails(reason);
      setErrorCode(details.code);
      setCorrelationId(details.correlationId);
      setMessage(`${details.message} Refresh the run and try again.`);
      setStatus("unavailable");
    }
  }, [connectionStatus, currentStageId, runId]);

  useEffect(() => { void refresh(); }, [refresh]);

  const plannedCommands = useMemo(() => Object.values(plan?.stage_plan.commands ?? {}).flat(), [plan]);
  const requestFor = useCallback((template: CommandTemplateDto, key: string): CommandPolicyValidateRequestDto | null => {
    const planned = plannedCommands.find((candidate) => candidate.command_id === template.command_id);
    const alias = planned?.working_directory_alias;
    const workingDirectory = alias ? workspaceAliases[alias] : undefined;
    if (!runId || !currentStageId || !plan || !planned || !alias || !workingDirectory) return null;
    return {
      run_id: runId,
      stage_id: currentStageId,
      command_id: template.command_id,
      template_id: template.template_id,
      template_version: template.version,
      plan_id: plan.plan.plan_id,
      plan_version: plan.plan.version,
      executable: template.executable,
      arguments: [...planned.arguments],
      cwd_alias: alias,
      working_directory_alias: alias,
      working_directory: workingDirectory,
      execution_profile_id: plan.stage_plan.execution_profile_id,
      network_profile: planned.network_profile,
      cancellation_policy: (planned as { cancellation_policy?: string }).cancellation_policy ?? "terminate_process_tree",
      timeout_seconds: planned.timeout_seconds,
      shell: false,
      expected_state_version: currentVersion,
      idempotency_key: key,
      requested_by: "control-tower",
      correlation_id: newCorrelationId(),
    };
  }, [currentStageId, currentVersion, plan, plannedCommands, runId, workspaceAliases]);

  function beginValidation(template: CommandTemplateDto, reuseKey?: string) {
    setSelectedTemplate(template);
    const key = reuseKey ?? `command-policy:${runId}:${currentStageId}:${template.template_id}:v${template.version}:state-${currentVersion}:${newCorrelationId()}`;
    const request = requestFor(template, key);
    if (!request) {
      setStatus("rejected");
      setErrorCode("PLAN_NOT_FOUND");
      setMessage("An approved stage plan and registered workspace are required before validation.");
      return;
    }
    attemptKey.current = key;
    setLastRequest(request);
    setValidationResult(null);
    setMessage(null);
    setErrorCode(null);
    setCorrelationId(request.correlation_id ?? null);
    setStatus("validating");
    void validateCommandPolicy(request).then((result) => {
      setValidationResult(result);
      setCorrelationId(result.correlation_id);
      setStatus(result.decision === "accepted" ? "accepted" : "rejected");
    }).catch(async (reason: unknown) => {
      const details = errorDetails(reason);
      setErrorCode(details.code);
      setCorrelationId(details.correlationId);
      setMessage(`${details.message} ${details.code === "STALE_STATE_VERSION" ? "Refresh the authoritative run; review the new state, then validate again." : "Review the guidance and retry when the backend is available."}`);
      if (details.code === "STALE_STATE_VERSION") {
        attemptKey.current = null;
        setStatus("stale");
        await refreshAuthoritativeState?.();
      } else {
        setStatus(details.code === "CONFLICT" ? "conflict" : "unavailable");
      }
    });
  }

  const canValidate = Boolean(runId && currentStageId && plan && Object.keys(workspaceAliases).length);
  return (
    <section className={styles.panel} aria-label="Command policy inspector">
      <div className={styles.previewHeader}><div><p className={styles.kicker}>S3-F01</p><h2>Command Policy Inspector</h2><p className={styles.note}>Backend-owned registry, plan, profile, and workspace policy.</p></div><strong>{status}</strong></div>
      {status === "loading" ? <p role="status">Loading registered commands and approved stage plan...</p> : null}
      {status === "reconnecting" ? <p role="status">Reconnecting; refreshing authoritative command policy...</p> : null}
      {status === "unavailable" ? <p role="alert">Backend unavailable. {message} {correlationId ? `Correlation ID: ${correlationId}` : ""}</p> : null}
      {status === "stale" ? <p role="alert">The run changed while this page was open. {message} Current state version: {currentVersion}. Refresh completed; validate again.</p> : null}
      {status === "conflict" ? <p role="alert">Authorization conflict. {message} {correlationId ? `Correlation ID: ${correlationId}` : ""}</p> : null}
      {!currentStageId && status === "ready" ? <p role="alert">No authoritative stage is selected for this run.</p> : null}
      {templates && templates.templates.length === 0 ? <p className={styles.note}>No registered command templates are available.</p> : null}
      {templates && templates.templates.length > 0 ? <><h3>Registered command templates</h3><ul className={styles.list}>{templates.templates.map((template) => <li key={template.template_id}><div><strong>{template.command_id} v{template.version}</strong><br /><code>{template.executable} {template.arguments.join(" ")}</code>{template.description ? <><br /><span className={styles.note}>{template.description}</span></> : null}</div><button type="button" onClick={() => beginValidation(template)} disabled={!canValidate || status === "validating"}>{status === "validating" && selectedTemplate?.template_id === template.template_id ? "Validating..." : "Validate against policy"}</button></li>)}</ul></> : null}
      {status === "ready" && !canValidate ? <p role="alert">Validation is blocked until the backend supplies an approved stage plan and registered workspace.</p> : null}
      {validationResult ? <><h3>Authorization decision</h3><div className={styles.dimensionGrid}><div><span>Decision</span><strong>{validationResult.decision.toUpperCase()}</strong></div><div><span>Command template</span><code>{validationResult.command_id} v{selectedTemplate?.version}</code></div><div><span>Sanitized preview</span><code>{validationResult.executable} {validationResult.arguments.join(" ")}</code></div><div><span>Execution profile</span><code>{validationResult.execution_profile_id}</code></div><div><span>Workspace alias</span><code>{validationResult.cwd_alias}</code></div><div><span>Network profile</span><code>{lastRequest?.network_profile}</code></div><div><span>State version used</span><code>{validationResult.expected_state_version}</code></div><div><span>Decision timestamp</span><code>{validationResult.decision_timestamp ?? "not supplied"}</code></div><div><span>Correlation ID</span><code>{validationResult.correlation_id ?? "not supplied"}</code></div></div>{validationResult.decision !== "accepted" ? <div role="alert"><p><strong>{validationResult.reasons[0]?.split(":")[0] ?? "POLICY_REJECTED"}</strong></p><p>{validationResult.reasons.join("; ") || "The backend rejected this command. Review the approved plan and retry."}</p></div> : null}{validationResult.artifact_id ? <p><a href={`/api/v1/artifacts/${encodeURIComponent(validationResult.artifact_id)}`} target="_blank" rel="noreferrer">Open authorization evidence {validationResult.artifact_id}</a></p> : null}{validationResult.idempotent_replay ? <p className={styles.note}>Idempotent replay: the backend returned the prior decision for this unchanged authorization attempt.</p> : null}</> : null}
      {status === "rejected" && !validationResult ? <p role="alert">{errorCode}: {message}</p> : null}
      {lastRequest && (status === "unavailable" || status === "conflict") ? <button type="button" onClick={() => selectedTemplate && beginValidation(selectedTemplate, attemptKey.current ?? undefined)}>Retry unchanged authorization</button> : null}
      {runId ? <CommandExecutionPanel runId={runId} stateVersion={currentVersion} authorization={validationResult} connectionStatus={connectionStatus} workflowEvents={workflowEvents ?? runState?.workflow_events} refreshAuthoritativeState={refreshAuthoritativeState} /> : null}
    </section>
  );
}
