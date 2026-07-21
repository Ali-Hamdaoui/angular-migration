"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiClientError } from "@/api/client";
import { createSandbox, decideG07, getG07Status, prepareStage } from "@/api/stages";
import type { G07DecisionRequest, G07ReviewResponse, StagePrepareResponse, StageSandboxResponse } from "@/api/stages";
import type { AuthoritativeRunStateDto } from "@/types/generated/api";
import styles from "./StagePreparationPanel.module.css";

type G07Decision = "approved" | "approved_with_comment" | "modification_requested" | "rejected";

interface TabInfo {
  id: "plan" | "profile" | "input";
  label: string;
}

const TABS: TabInfo[] = [
  { id: "plan", label: "Plan" },
  { id: "profile", label: "Profile" },
  { id: "input", label: "Input" },
];


export function StagePreparationPanel({
  runId,
  stageId,
  initialState,
  prepareBindings,
  connectionStatus = "open",
  refreshAuthoritativeState,
}: {
  runId: string;
  stageId?: string;
  initialState: AuthoritativeRunStateDto;
  prepareBindings?: { stage_key?: string; source_version_family?: string; target_version_family?: string; plan_version?: string };
  connectionStatus?: string;
  refreshAuthoritativeState?: () => Promise<void>;
}) {
  const [preparation, setPreparation] = useState<StagePrepareResponse | null>(null);
  const [sandbox, setSandbox] = useState<StageSandboxResponse | null>(null);
  const [g07, setG07] = useState<G07ReviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);
  const [activeTab, setActiveTab] = useState<"plan" | "profile" | "input">("plan");
  const [g07Decision, setG07Decision] = useState<G07Decision>("approved");
  const [g07Comment, setG07Comment] = useState("");
  const [authoritativeStageId, setAuthoritativeStageId] = useState(stageId);
  const operationKeys = useRef(new Map<string, string>());
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  useEffect(() => { setAuthoritativeStageId(stageId); }, [stageId]);

  const stableKey = (scope: string) => {
    const existing = operationKeys.current.get(scope);
    if (existing) return existing;
    const key = `stage-prep-${scope}`;
    operationKeys.current.set(scope, key);
    return key;
  };

  const refresh = useCallback(async (requestedStageId?: string) => {
    setLoading(true);
    setError(null);
    setReconnecting(false);
    try {
      const currentStageId = requestedStageId ?? authoritativeStageId;
      const g07Status = currentStageId ? await getG07Status(runId, currentStageId).catch((reason: unknown) => {
          if (reason instanceof ApiClientError && reason.status === 404) return null;
          throw reason;
        }) : null;
      setG07(g07Status);
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status >= 500) {
        setReconnecting(true);
      } else {
        setError("Stage preparation evidence could not be loaded.");
      }
    } finally {
      setLoading(false);
    }
  }, [runId, authoritativeStageId]);

  useEffect(() => { void refresh(); }, [refresh]);

  async function handlePrepare() {
    if (!authoritativeStageId && !prepareBindings?.stage_key) return;
    setWorking("prepare");
    setError(null);
    setStale(false);
    try {
      const pkg = (g07?.package ?? {}) as Record<string, unknown>;
      const stageKey = String(pkg.stage_key ?? prepareBindings?.stage_key ?? authoritativeStageId);
      const sourceFamily = String(pkg.source_version_family ?? pkg.source_family ?? prepareBindings?.source_version_family ?? "");
      const targetFamily = String(pkg.target_version_family ?? pkg.target_family ?? prepareBindings?.target_version_family ?? "");
      const planVersion = String(pkg.plan_version ?? prepareBindings?.plan_version ?? "");
      if (!sourceFamily || !targetFamily || !planVersion) {
        setError("Current stage plan bindings are not available.");
        return;
      }
      const result = await prepareStage(runId, stageKey, {
        expected_state_version: initialState.state_version,
        idempotency_key: stableKey(`prepare:${runId}:${stageKey}:${initialState.state_version}:${planVersion}`),
        actor: "control-tower",
        stage_key: stageKey,
        source_version_family: sourceFamily,
        target_version_family: targetFamily,
        plan_version: planVersion,
      });
      setPreparation(result);
      setAuthoritativeStageId(result.stage_id);
      await refreshAuthoritativeState?.();
      await refresh(result.stage_id);
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 409) {
        setStale(true);
        await refreshAuthoritativeState?.();
        await refresh();
      }
      else setError("Stage preparation could not be started.");
    } finally {
      setWorking(null);
    }
  }

  async function handleCreateSandbox() {
    if (!authoritativeStageId || !g07) return;
    setWorking("sandbox");
    setError(null);
    setStale(false);
    try {
      const result = await createSandbox(runId, authoritativeStageId, {
        expected_state_version: g07.state_version,
        idempotency_key: stableKey(`sandbox:${authoritativeStageId}:${g07.state_version}:${g07.gate_version}:${JSON.stringify(g07.package)}`),
        actor: "control-tower",
      });
      // The POST response is diagnostic only; readiness is established by the
      // authoritative workflow projection/event in the subsequent slice.
      setSandbox(result.status === "sandbox_ready" ? { ...result, status: "creating_sandbox" } : result);
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 409) {
        setStale(true);
        await refreshAuthoritativeState?.();
        await refresh();
      }
      else setError("Sandbox creation could not be completed.");
    } finally {
      setWorking(null);
    }
  }

  async function handleG07Decision() {
    if (!g07 || !authoritativeStageId) return;
    setWorking("g07");
    setError(null);
    setStale(false);
    const normalizedComment = g07Comment.trim() || null;
    if ((g07Decision === "approved_with_comment" || g07Decision === "modification_requested") && !normalizedComment) {
      setError("A non-empty comment is required for this decision.");
      setWorking(null);
      return;
    }
    try {
      const request: G07DecisionRequest = {
        expected_state_version: g07.state_version,
        idempotency_key: stableKey(`g07:${authoritativeStageId}:${g07.state_version}:${g07.gate_version}:${g07Decision}:${normalizedComment ?? ""}`),
        actor: "control-tower",
        stage_id: authoritativeStageId,
        decision: g07Decision,
        comment: normalizedComment,
        gate_id: g07.gate_id,
      };
      const result = await decideG07(runId, request);
      setG07(result);
      await refreshAuthoritativeState?.();
      await refresh();
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 409) {
        setStale(true);
        await refreshAuthoritativeState?.();
        await refresh();
      }
      else setError("G07 decision could not be recorded.");
    } finally {
      setWorking(null);
    }
  }

  const status = sandbox?.status ?? preparation?.status ?? "not_started";
  const currentStageEvents = authoritativeStageId
    ? initialState.workflow_events.filter((event) => event.stage_id === authoritativeStageId).sort((a, b) => a.sequence - b.sequence)
    : [];
  const latestStageEvent = currentStageEvents[currentStageEvents.length - 1];
  const eventStatus = latestStageEvent?.event_type === "STAGE_SANDBOX_READY" ? "sandbox_ready"
    : latestStageEvent?.event_type === "STAGE_PREPARING" ? "preparing"
      : latestStageEvent?.event_type === "STAGE_PLAN_LOCKED" ? "plan_locked"
        : latestStageEvent?.event_type === "STAGE_WAITING_APPROVAL" || latestStageEvent?.event_type === "G07_CREATED" ? "waiting_approval"
          : latestStageEvent?.event_type === "G07_STALE" ? "stale"
            : latestStageEvent?.event_type === "G07_MODIFICATION_REQUESTED" ? "modification_requested"
              : latestStageEvent?.event_type === "G07_REJECTED" ? "rejected"
                : latestStageEvent?.event_type === "G07_APPROVED" ? "approved"
                  : null;
  const eventBlocksApproval = eventStatus === "stale" || eventStatus === "modification_requested" || eventStatus === "rejected";
  const g07Approved = !stale && !eventBlocksApproval && (g07?.status === "approved" || g07?.status === "approved_with_comment" || eventStatus === "approved");
  const displayStatus = eventStatus ?? status;
  const g07Blocked = g07?.status === "rejected" || g07?.status === "modification_requested";
  const sandboxReady = latestStageEvent?.event_type === "STAGE_SANDBOX_READY";
  const inProgress = status === "preparing" || status === "creating_sandbox";
  const blocked = status === "waiting_approval" || status === "g07_required" || Boolean(preparation?.plan === null && !loading);
  const verification = sandbox?.verification as Record<string, unknown> | null | undefined;
  const currentPackage = (g07?.package ?? {}) as Record<string, unknown>;
  const artifactLinks = (g07?.package?.artifact_links as Record<string, unknown> | undefined) ?? {};
  const artifactIds = Array.from(new Set([
    ...((g07?.package?.artifact_ids as string[] | undefined) ?? []),
    typeof verification?.copy_report_artifact_id === "string" ? verification.copy_report_artifact_id : "",
    typeof verification?.verification_artifact_id === "string" ? verification.verification_artifact_id : "",
  ].filter(Boolean)));
  const selectTab = (index: number) => {
    const next = (index + TABS.length) % TABS.length;
    setActiveTab(TABS[next].id);
    tabRefs.current[next]?.focus();
  };

  return (
    <section className={styles.panel} aria-labelledby="stage-preparation-title">
      <div className={styles.header}>
        <div>
          <p className={styles.kicker}>S3-F05</p>
          <h2 id="stage-preparation-title">Stage workspace preparation</h2>
          <p className={styles.note}>Prepare the stage sandbox, verify plan/profile/input, and satisfy the G07 boundary.</p>
        </div>
        <span className={styles.status}>{displayStatus.replaceAll("_", " ")}</span>
      </div>

      {loading ? <p role="status" className={styles.statusMessage}>Loading stage preparation evidence…</p> : null}

      {!loading && reconnecting ? (
        <p role="alert" className={styles.errorMessage}>Connection lost. Reconnecting to backend…</p>
      ) : null}

      {error ? <p role="alert" className={styles.errorMessage}>{error}</p> : null}

      {stale ? (
        <p role="alert" className={styles.warningMessage}>
          The run state changed while processing. Refresh the authoritative state before retrying.
        </p>
      ) : null}

      {!loading && !preparation && !error ? (
        <p className={styles.note}>No stage preparation has been initiated.</p>
      ) : null}
      <p className={styles.note} role="note">
        Risk notice: changed plan, input, or gate bindings invalidate approval; readiness is controlled by the durable stage event.
      </p>

      {/* Readiness status */}
      {!loading && (preparation || sandboxReady) ? (
        <div className={styles.readinessBar}>
          <span>Stage readiness:</span>
          {sandboxReady ? (
            <strong className={styles.readyLabel}>Sandbox ready</strong>
          ) : inProgress ? (
            <strong className={styles.inProgressLabel}>In progress</strong>
          ) : blocked ? (
            <strong className={styles.blockedLabel}>Blocked</strong>
          ) : (
            <strong className={styles.pendingLabel}>Not ready</strong>
          )}
        </div>
      ) : null}

      {/* Plan | Profile | Input tabs */}
      {!loading && preparation ? (
        <div className={styles.tabSection}>
          <div className={styles.tabBar} role="tablist">
            {TABS.map((tab, index) => (
              <button
                key={tab.id}
                id={`stage-tab-${tab.id}`}
                role="tab"
                className={`${styles.tab} ${activeTab === tab.id ? styles.tabActive : ""}`}
                onClick={() => setActiveTab(tab.id)}
                aria-selected={activeTab === tab.id}
                aria-controls={`stage-tabpanel-${tab.id}`}
                tabIndex={activeTab === tab.id ? 0 : -1}
                ref={(element) => { tabRefs.current[index] = element; }}
                onKeyDown={(event) => {
                  const index = TABS.findIndex((item) => item.id === tab.id);
                  if (event.key === "ArrowRight") { event.preventDefault(); selectTab(index + 1); }
                  if (event.key === "ArrowLeft") { event.preventDefault(); selectTab(index - 1); }
                  if (event.key === "Home") { event.preventDefault(); selectTab(0); }
                  if (event.key === "End") { event.preventDefault(); selectTab(TABS.length - 1); }
                }}
              >
                {tab.label}
              </button>
            ))}
          </div>
          <div className={styles.tabContent}>
            {activeTab === "plan" ? (
              <div className={styles.tabPane} id="stage-tabpanel-plan" role="tabpanel" aria-labelledby="stage-tab-plan">
                <h3>Execution plan</h3>
                {preparation.plan ? (
                  <pre className={styles.codeBlock}>{JSON.stringify(preparation.plan, null, 2)}</pre>
                ) : (
                  <p className={styles.note}>No execution plan has been generated yet.</p>
                )}
              </div>
            ) : activeTab === "profile" ? (
              <div className={styles.tabPane} id="stage-tabpanel-profile" role="tabpanel" aria-labelledby="stage-tab-profile">
                <h3>Runtime profile</h3>
                <dl className={styles.metadataGrid}>
                  <div><dt>Source family</dt><dd>{String(currentPackage.source_version_family ?? currentPackage.source_family ?? prepareBindings?.source_version_family ?? "not yet available")}</dd></div>
                  <div><dt>Target family</dt><dd>{String(currentPackage.target_version_family ?? currentPackage.target_family ?? prepareBindings?.target_version_family ?? "not yet available")}</dd></div>
                  <div><dt>Plan version</dt><dd>{String(currentPackage.plan_version ?? prepareBindings?.plan_version ?? "not yet available")}</dd></div>
                  <div><dt>State version</dt><dd>{initialState.state_version}</dd></div>
                </dl>
              </div>
            ) : (
              <div className={styles.tabPane} id="stage-tabpanel-input" role="tabpanel" aria-labelledby="stage-tab-input">
                <h3>Stage input summary</h3>
                <dl className={styles.metadataGrid}>
                  <div><dt>Run</dt><dd><code>{runId}</code></dd></div>
          <div><dt>Stage</dt><dd><code>{authoritativeStageId ?? "not prepared"}</code></dd></div>
                  <div><dt>Status</dt><dd>{displayStatus.replaceAll("_", " ")}</dd></div>
                  <div><dt>Idempotent</dt><dd>{preparation.idempotent_replay ? "yes (replay)" : "no"}</dd></div>
                </dl>
              </div>
            )}
          </div>
        </div>
      ) : null}

      {/* G07 decision panel */}
      {!loading && g07 && !g07Approved ? (
        <div className={styles.g07Panel}>
          <div className={styles.g07Header}>
            <h3>G07 boundary review</h3>
            <span className={`${styles.g07Badge} ${g07Blocked ? styles.g07Blocked : styles.g07Pending}`}>
              {eventStatus ?? g07.status?.replaceAll("_", " ") ?? "pending"}
            </span>
          </div>
          {g07.package ? (
            <dl className={styles.metadataGrid}>
              <div><dt>Gate version</dt><dd>{g07.gate_version}</dd></div>
              <div><dt>State version</dt><dd>{g07.state_version}</dd></div>
              <div><dt>Stale reason</dt><dd>{g07.stale_reason ?? "none"}</dd></div>
            </dl>
          ) : null}
          {g07Blocked ? (
            <p role="alert" className={styles.warningMessage}>
              G07 review was not approved. Stage preparation cannot proceed until G07 is satisfied.
            </p>
          ) : null}
          <div className={styles.g07Controls}>
            <label htmlFor="g07-decision" className={styles.controlLabel}>Decision</label>
            <select
              id="g07-decision"
              className={styles.selectInput}
              value={g07Decision}
              onChange={(e) => setG07Decision(e.target.value as G07Decision)}
            >
              <option value="approved">Approve G07</option>
              <option value="approved_with_comment">Approve with comment</option>
              <option value="modification_requested">Request modification</option>
              <option value="rejected">Reject G07</option>
            </select>
            <label htmlFor="g07-comment" className={styles.controlLabel}>Comment</label>
            <textarea
              id="g07-comment"
              className={styles.textInput}
              value={g07Comment}
              onChange={(e) => setG07Comment(e.target.value)}
              rows={3}
              placeholder="Optional rationale for the decision."
            />
            <button
              type="button"
              className={styles.actionButton}
              disabled={working !== null || !authoritativeStageId || connectionStatus !== "open"}
              onClick={handleG07Decision}
            >
              {working === "g07" ? "Recording…" : "Record G07 decision"}
            </button>
          </div>
        </div>
      ) : null}

      {!loading && g07 && g07Approved ? (
        <p className={styles.successMessage}>G07 boundary review approved.</p>
      ) : null}

      {!loading && preparation && !sandbox ? (
        <div className={styles.verificationBlock}>
          <h3>Sandbox evidence</h3>
          <p className={styles.note}>Copy and verification evidence not yet available.</p>
          {artifactIds.length ? artifactIds.map((artifactId) => {
            const supplied = typeof artifactLinks[artifactId] === "string" ? artifactLinks[artifactId] as string : `/api/v1/artifacts/${encodeURIComponent(artifactId)}`;
            return <div key={artifactId}><a href={supplied} target="_blank" rel="noreferrer">{artifactId}</a></div>;
          }) : null}
        </div>
      ) : null}

      {/* Sandbox copy progress */}
      {!loading && sandbox ? (
        <div className={styles.sandboxSection}>
          <h3>Sandbox</h3>
          <dl className={styles.metadataGrid}>
            <div><dt>Status</dt><dd>{sandbox.status.replaceAll("_", " ")}</dd></div>
            <div><dt>State version</dt><dd>{sandbox.state_version}</dd></div>
            <div><dt>Event sequence</dt><dd>{sandbox.event_sequence}</dd></div>
          </dl>
          {sandbox.verification ? (
            <div className={styles.verificationBlock}>
              <h4>Sandbox verification</h4>
              <dl className={styles.metadataGrid}>
                <div><dt>Workspace alias</dt><dd>{String(verification?.workspace_alias ?? verification?.workspace_id ?? "not yet available")}</dd></div>
                <div><dt>Copy outcome</dt><dd>{String(verification?.copy_status ?? verification?.copy_outcome ?? "not yet available")}</dd></div>
                <div><dt>Copied files</dt><dd>{String(verification?.file_count ?? "not yet available")}</dd></div>
                <div><dt>Total bytes</dt><dd>{String(verification?.total_size_bytes ?? verification?.total_bytes ?? "not yet available")}</dd></div>
                <div><dt>Source fingerprint</dt><dd>{String(verification?.source_fingerprint ?? "not yet available")}</dd></div>
                <div><dt>Sandbox fingerprint</dt><dd>{String(verification?.sandbox_fingerprint ?? "not yet available")}</dd></div>
                <div><dt>Verification</dt><dd>{String(verification?.verified ?? verification?.verification_result ?? "not yet available")}</dd></div>
                <div><dt>Reconstructed</dt><dd>{String(verification?.reconstruction ?? verification?.reconstructed ?? "not yet available")}</dd></div>
                <div><dt>Copy-report artifact</dt><dd>{String(verification?.copy_report_artifact_id ?? "not yet available")} {String(verification?.copy_report_checksum ?? "")}</dd></div>
                <div><dt>Verification artifact</dt><dd>{String(verification?.verification_artifact_id ?? "not yet available")} {String(verification?.verification_checksum ?? "")}</dd></div>
              </dl>
            </div>
          ) : null}
          <div className={styles.verificationBlock}>
            <h4>Evidence artifacts</h4>
            {artifactIds.length ? artifactIds.map((artifactId) => {
              const supplied = typeof artifactLinks[artifactId] === "string" ? artifactLinks[artifactId] as string : `/api/v1/artifacts/${encodeURIComponent(artifactId)}`;
              return <div key={artifactId}><a href={supplied} target="_blank" rel="noreferrer">{artifactId}</a></div>;
            }) : <p className={styles.note}>Evidence artifacts not yet available.</p>}
          </div>
        </div>
      ) : null}

      {/* Action buttons */}
      <div className={styles.actions}>
        <span>State version {initialState.state_version}</span>
        <div className={styles.actionButtons}>
          {!loading && !sandboxReady && (!preparation || preparation.status === "not_started") ? (
            <button
              type="button"
              className={`${styles.actionButton} ${styles.primaryButton}`}
              disabled={working !== null || connectionStatus !== "open" || (!authoritativeStageId && !prepareBindings?.stage_key)}
              onClick={handlePrepare}
            >
              {working === "prepare" ? "Preparing…" : "Prepare stage"}
            </button>
          ) : null}
          {!loading && preparation && !sandbox ? (
            <button
              type="button"
              className={`${styles.actionButton} ${styles.primaryButton}`}
              disabled={working !== null || !g07Approved || connectionStatus !== "open" || !authoritativeStageId}
              onClick={handleCreateSandbox}
            >
              {working === "sandbox" ? "Creating sandbox…" : "Create sandbox"}
            </button>
          ) : null}
          {!loading && sandbox && !sandboxReady ? (
            <button
              type="button"
              className={`${styles.actionButton} ${styles.primaryButton}`}
              disabled={working !== null || !g07Approved || connectionStatus !== "open" || !authoritativeStageId}
              onClick={handleCreateSandbox}
            >
              {working === "sandbox" ? "Retrying…" : "Retry sandbox creation"}
            </button>
          ) : null}
          {!loading && sandboxReady ? (
            <span className={styles.readyNotice}>Sandbox is ready. Proceed to bootstrap installation.</span>
          ) : null}
        </div>
      </div>
    </section>
  );
}
