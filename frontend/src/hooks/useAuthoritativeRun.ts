"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getBackendBaseUrl } from "@/api/client";
import { getAuthoritativeRunState } from "@/api/runs";
import type { AuthoritativeRunStateDto, WorkflowEventDto } from "@/types/generated/api";

export type AuthoritativeConnectionStatus = "loading" | "connecting" | "open" | "reconnecting" | "recovering" | "failed";

export const AUTHORITATIVE_EVENT_TYPES = ["RUN_CREATED", "RUN_START_ACCEPTED", "RUN_STARTED", "RUN_START_REJECTED", "run_state_changed", "SOURCE_INTAKE_QUEUED", "SOURCE_INTAKE_STARTED", "SOURCE_INTAKE_COMPLETED", "SOURCE_INTAKE_FAILED", "RUN_RECONSTRUCTED", "SNAPSHOT_STARTED", "SNAPSHOT_CREATED", "SNAPSHOT_FAILED", "SNAPSHOT_PROGRESS_UPDATED", "SNAPSHOT_QUARANTINED", "SOURCE_INTEGRITY_VERIFIED", "SOURCE_INTEGRITY_FAILED", "G02_CREATED", "G02_APPROVED", "G02_REJECTED", "G02_STALE", "ANALYSIS_AGENT_STARTED", "ANALYSIS_AGENT_COMPLETED", "ANALYSIS_AGENT_FAILED", "ANALYSIS_REVIEWER_STARTED", "ANALYSIS_REVIEWER_COMPLETED", "ANALYSIS_REVIEWER_FAILED", "G04_CREATED", "G04_APPROVED", "G04_MODIFICATION_REQUESTED", "G04_REJECTED", "G04_STALE", "COMPATIBILITY_RESOLUTION_STARTED", "COMPATIBILITY_RESOLUTION_COMPLETED", "COMPATIBILITY_RESOLUTION_BLOCKED", "G05_CREATED", "G05_APPROVED", "G05_MODIFICATION_REQUESTED", "G05_REJECTED", "G05_STALE", "MIGRATION_PLAN_CREATED", "STAGE_PLAN_CREATED", "PLAN_REVISION_CREATED", "APPROVAL_MARKED_STALE", "PLANNING_AGENT_COMPLETED", "G06_CREATED", "G06_APPROVED", "G06_MODIFICATION_REQUESTED", "G06_REJECTED", "G06_STALE", "EXECUTION_PROFILE_RESOLUTION_STARTED", "EXECUTION_PROFILE_RESOLVED", "EXECUTION_PROFILE_BLOCKED", "EXECUTION_PROFILE_SELECTED", "BASELINE_WORKSPACE_STARTED", "BASELINE_WORKSPACE_READY", "COMMAND_QUEUED", "COMMAND_STARTED", "COMMAND_SUCCEEDED", "COMMAND_FAILED", "COMMAND_OUTPUT_AVAILABLE", "COMMAND_OUTPUT_CHUNK", "BASELINE_INSTALL_SUCCEEDED", "BASELINE_INSTALL_FAILED", "COMMAND_CANCELLED", "COMMAND_INTERRUPTED", "BASELINE_TARGETS_DISCOVERED", "BASELINE_BUILD_STARTED", "BASELINE_BUILD_COMPLETED", "BASELINE_TESTS_STARTED", "BASELINE_TESTS_COMPLETED", "BASELINE_LINT_STARTED", "BASELINE_LINT_COMPLETED", "BASELINE_QUALIFIED", "G03_CREATED", "G03_APPROVED", "G03_REJECTED", "BASELINE_FAILURES_FINGERPRINTED", "BASELINE_ROUTE_ANCHOR_CREATED", "BASELINE_BACKEND_ANCHOR_CREATED", "DISCOVERY_STARTED", "SCANNER_COMPLETED", "DISCOVERY_COMPLETED", "DISCOVERY_BLOCKED"] as const;

export const PARITY_BASELINE_EVENT_TYPES = ["PARITY_BASELINE_STARTED", "PARITY_BASELINE_COMPLETED", "PARITY_BASELINE_BLOCKED"] as const;
export const LLM_EVENT_TYPES = ['LLM_INVOCATION_STARTED', 'LLM_INVOCATION_COMPLETED', 'LLM_INVOCATION_FAILED', 'LLM_BUDGET_WARNING', 'LLM_BUDGET_BLOCKED'] as const;
export const TRANSFORMATION_EVENT_TYPES = [
  "TRANSFORMATION_CONTINUATION_CREATED", "TRANSFORMATION_CONTINUATION_CLAIMED", "TRANSFORMATION_CONTINUATION_WAITING",
  "TRANSFORMATION_CONTINUATION_RESUMED", "TRANSFORMATION_CONTINUATION_FAILED", "TRANSFORMATION_CONTINUATION_COMPLETED",
  "TRANSFORMATION_CANCEL_REQUESTED", "TRANSFORMATION_CANCELLED", "STAGE_INPUT_CHECKPOINT_CREATED",
  "STAGE_WORKSPACE_RECONSTRUCTION_STARTED", "STAGE_WORKSPACE_RECONSTRUCTED", "STAGE_WORKSPACE_FINGERPRINT_MISMATCH",
  "STAGE_RUNTIME_PROFILE_VALIDATED", "STAGE_RUNTIME_PROFILE_BLOCKED", "COMPATIBILITY_PREFLIGHT_STARTED",
  "COMPATIBILITY_PREFLIGHT_PASSED", "COMPATIBILITY_PREFLIGHT_BLOCKED", "KNOWN_STAGE_DECISION_REQUIRED",
  "KNOWN_STAGE_DECISION_RECORDED", "G07_CREATED", "G07_APPROVED", "G07_REJECTED", "G07_STALE",
  "STAGE_BOOTSTRAP_VERIFIED", "STAGE_TRANSFORMATION_STARTED", "CLI_PROMPT_CAPTURED",
  "CLI_PROMPT_EXPLANATION_COMPLETED", "CLI_PROMPT_DECIDED", "COMMAND_RECONSTRUCTION_REQUIRED",
  "VERSION_VERIFICATION_PASSED", "VERSION_VERIFICATION_FAILED", "STAGE_TRANSFORMATION_COMPLETED",
  "G08_CREATED", "G08_APPROVED", "G08_REJECTED", "G08_STALE", "STAGE_VALIDATION_STARTED",
  "STAGE_VALIDATION_COMPLETED", "STAGE_VALIDATION_FAILED", "G09_CREATED", "G09_APPROVED", "G09_REJECTED",
  "G09_STALE", "FAILURE_EVIDENCE_FROZEN", "FAILURE_CLASSIFIED", "REPAIR_PROPOSAL_CREATED",
  "REPAIR_REVIEW_COMPLETED", "G10_CREATED", "G10_APPROVED", "G10_REJECTED", "G10_STALE",
  "REPAIR_APPLY_STARTED", "REPAIR_APPLY_COMPLETED", "REPAIR_APPLY_FAILED", "REPAIR_REVALIDATION_COMPLETED",
  "G11_CREATED", "G11_APPROVED", "G11_REJECTED", "G11_STALE", "G12_CREATED", "G12_APPROVED",
  "G12_REJECTED", "G12_STALE", "STAGE_SEALED", "NEXT_STAGE_MATERIALIZED", "FINAL_TARGET_VERIFIED",
  "STAGED_MIGRATION_COMPLETED",
] as const;

export function useAuthoritativeRun(runId: string, initialState: AuthoritativeRunStateDto) {
  const [state, setState] = useState(initialState);
  const [status, setStatus] = useState<AuthoritativeConnectionStatus>("connecting");
  const [error, setError] = useState<string | null>(null);
  const stateRef = useRef(initialState);
  const latestSequenceRef = useRef(Math.max(0, ...initialState.workflow_events.map((event) => event.sequence)));
  const seenEventIdsRef = useRef(new Set(initialState.workflow_events.map((event) => event.event_id)));
  const statusRef = useRef<AuthoritativeConnectionStatus>("connecting");
  const recoveryInProgressRef = useRef(false);

  const setConnectionStatus = useCallback((next: AuthoritativeConnectionStatus) => {
    statusRef.current = next;
    setStatus(next);
  }, []);

  const refresh = useCallback(() => {
    recoveryInProgressRef.current = true;
    setConnectionStatus("recovering");
    return getAuthoritativeRunState(runId)
      .then((next) => {
        const recovered = {
          ...next,
          workflow_events: [...next.workflow_events].sort((a, b) => a.sequence - b.sequence),
        };
        stateRef.current = recovered;
        latestSequenceRef.current = Math.max(0, ...recovered.workflow_events.map((event) => event.sequence));
        seenEventIdsRef.current = new Set(recovered.workflow_events.map((event) => event.event_id));
        setState(recovered);
        setError(null);
        recoveryInProgressRef.current = false;
        setConnectionStatus("open");
      })
      .catch(() => {
        setError("The authoritative run state could not be refreshed.");
        recoveryInProgressRef.current = false;
        setConnectionStatus("failed");
      });
  }, [runId, setConnectionStatus]);

  useEffect(() => {
    let active = true;
    const source = new EventSource(`${getBackendBaseUrl()}/api/v1/runs/${encodeURIComponent(runId)}/events`);
    const onEvent = (event: MessageEvent) => {
      try {
        const next = JSON.parse(event.data) as WorkflowEventDto;
        if (seenEventIdsRef.current.has(next.event_id) || next.sequence <= latestSequenceRef.current) return;
        if (next.sequence > latestSequenceRef.current + 1) {
          if (!recoveryInProgressRef.current) void refresh();
          return;
        }
        seenEventIdsRef.current.add(next.event_id);
        latestSequenceRef.current = next.sequence;
        const projected = { ...stateRef.current, workflow_events: [...stateRef.current.workflow_events, next].sort((a, b) => a.sequence - b.sequence), updated_at: next.occurred_at };
        stateRef.current = projected;
        setState(projected);
      } catch {
        setError("The backend sent an invalid run event.");
      }
    };
    source.onopen = () => {
      if (statusRef.current === "reconnecting" || recoveryInProgressRef.current) {
        void refresh();
      } else {
        setConnectionStatus("open");
      }
    };
    source.onerror = () => {
      if (active) {
        setConnectionStatus("reconnecting");
        if (!recoveryInProgressRef.current) void refresh();
      }
    };
    for (const type of [...AUTHORITATIVE_EVENT_TYPES, ...PARITY_BASELINE_EVENT_TYPES, ...LLM_EVENT_TYPES, ...TRANSFORMATION_EVENT_TYPES]) source.addEventListener(type, onEvent);
    const interval = window.setInterval(() => { void refresh(); }, 5000);
    void refresh();
    return () => {
      active = false;
      window.clearInterval(interval);
      for (const type of [...AUTHORITATIVE_EVENT_TYPES, ...PARITY_BASELINE_EVENT_TYPES, ...LLM_EVENT_TYPES, ...TRANSFORMATION_EVENT_TYPES]) source.removeEventListener(type, onEvent);
      source.close();
    };
  }, [refresh, runId, setConnectionStatus]);

  return { state, status, error, refresh };
}

