"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiClientError } from "@/api/client";
import { createSandbox, decideG07, getG07Status, prepareStage } from "@/api/stages";
import type { G07DecisionRequest, G07ReviewResponse, StagePrepareResponse, StageSandboxResponse } from "@/api/stages";
import type { AuthoritativeRunStateDto } from "@/types/generated/api";
import styles from "./StagePreparationPanel.module.css";

type G07Decision = "approved" | "rejected";

interface TabInfo {
  id: "plan" | "profile" | "input";
  label: string;
}

const TABS: TabInfo[] = [
  { id: "plan", label: "Plan" },
  { id: "profile", label: "Profile" },
  { id: "input", label: "Input" },
];

const TERMINAL = new Set(["sandbox_ready", "failed", "cancelled"]);

function nextKey(runId: string, op: string) {
  return `stage-prep-${op}-${runId}-${Date.now()}`;
}

export function StagePreparationPanel({
  runId,
  stageId,
  initialState,
}: {
  runId: string;
  stageId: string;
  initialState: AuthoritativeRunStateDto;
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

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    setReconnecting(false);
    try {
      const [prep, sb, g07Status] = await Promise.all([
        prepareStage(runId, stageId, {
          expected_state_version: initialState.state_version,
          idempotency_key: nextKey(runId, "refresh"),
          actor: "control-tower",
          stage_key: stageId,
          source_version_family: "detected",
          target_version_family: "resolved",
          plan_version: "latest",
        }).catch((reason: unknown) => {
          if (reason instanceof ApiClientError && reason.status === 404) return null;
          throw reason;
        }),
        createSandbox(runId, stageId, {
          expected_state_version: initialState.state_version,
          idempotency_key: nextKey(runId, "sandbox-refresh"),
          actor: "control-tower",
        }).catch((reason: unknown) => {
          if (reason instanceof ApiClientError && reason.status === 404) return null;
          throw reason;
        }),
        getG07Status(runId, stageId).catch((reason: unknown) => {
          if (reason instanceof ApiClientError && reason.status === 404) return null;
          throw reason;
        }),
      ]);
      setPreparation(prep);
      setSandbox(sb);
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
  }, [runId, stageId, initialState.state_version]);

  useEffect(() => { void refresh(); }, [refresh]);

  async function handlePrepare() {
    setWorking("prepare");
    setError(null);
    setStale(false);
    try {
      const result = await prepareStage(runId, stageId, {
        expected_state_version: initialState.state_version,
        idempotency_key: nextKey(runId, "prepare"),
        actor: "control-tower",
        stage_key: stageId,
        source_version_family: "detected",
        target_version_family: "resolved",
        plan_version: "latest",
      });
      setPreparation(result);
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 409) setStale(true);
      else setError("Stage preparation could not be started.");
    } finally {
      setWorking(null);
    }
  }

  async function handleCreateSandbox() {
    setWorking("sandbox");
    setError(null);
    setStale(false);
    try {
      const result = await createSandbox(runId, stageId, {
        expected_state_version: initialState.state_version,
        idempotency_key: nextKey(runId, "sandbox"),
        actor: "control-tower",
      });
      setSandbox(result);
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 409) setStale(true);
      else setError("Sandbox creation could not be completed.");
    } finally {
      setWorking(null);
    }
  }

  async function handleG07Decision() {
    if (!g07) return;
    setWorking("g07");
    setError(null);
    setStale(false);
    try {
      const request: G07DecisionRequest = {
        expected_state_version: g07.state_version,
        idempotency_key: `g07-${runId}-${g07Decision}-${Date.now()}`,
        actor: "control-tower",
        stage_id: stageId,
        decision: g07Decision,
        comment: g07Comment.trim() || null,
      };
      const result = await decideG07(runId, request);
      setG07(result);
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 409) setStale(true);
      else setError("G07 decision could not be recorded.");
    } finally {
      setWorking(null);
    }
  }

  const status = sandbox?.status ?? preparation?.status ?? "not_started";
  const g07Approved = g07?.status === "approved" || g07?.status === "approved_with_comment";
  const g07Blocked = g07?.status === "rejected" || g07?.status === "modification_requested";
  const sandboxReady = status === "sandbox_ready";
  const inProgress = status === "preparing" || status === "creating_sandbox";
  const blocked = status === "waiting_approval" || status === "g07_required" || Boolean(preparation?.plan === null && !loading);

  return (
    <section className={styles.panel} aria-labelledby="stage-preparation-title">
      <div className={styles.header}>
        <div>
          <p className={styles.kicker}>S3-F05</p>
          <h2 id="stage-preparation-title">Stage workspace preparation</h2>
          <p className={styles.note}>Prepare the stage sandbox, verify plan/profile/input, and satisfy the G07 boundary.</p>
        </div>
        <span className={styles.status}>{status.replaceAll("_", " ")}</span>
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

      {/* Readiness status */}
      {!loading && preparation ? (
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
            {TABS.map((tab) => (
              <button
                key={tab.id}
                id={`stage-tab-${tab.id}`}
                role="tab"
                className={`${styles.tab} ${activeTab === tab.id ? styles.tabActive : ""}`}
                onClick={() => setActiveTab(tab.id)}
                aria-selected={activeTab === tab.id}
                aria-controls={`stage-tabpanel-${tab.id}`}
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
                  <div><dt>Source family</dt><dd>detected</dd></div>
                  <div><dt>Target family</dt><dd>resolved</dd></div>
                  <div><dt>Plan version</dt><dd>latest</dd></div>
                  <div><dt>State version</dt><dd>{initialState.state_version}</dd></div>
                </dl>
              </div>
            ) : (
              <div className={styles.tabPane} id="stage-tabpanel-input" role="tabpanel" aria-labelledby="stage-tab-input">
                <h3>Stage input summary</h3>
                <dl className={styles.metadataGrid}>
                  <div><dt>Run</dt><dd><code>{runId}</code></dd></div>
                  <div><dt>Stage</dt><dd><code>{stageId}</code></dd></div>
                  <div><dt>Status</dt><dd>{status.replaceAll("_", " ")}</dd></div>
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
              {g07.status?.replaceAll("_", " ") ?? "pending"}
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
              disabled={working !== null}
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

      {/* Sandbox copy progress */}
      {!loading && sandbox ? (
        <div className={styles.sandboxSection}>
          <h3>Sandbox</h3>
          <dl className={styles.metadataGrid}>
            <div><dt>Path</dt><dd><code>{sandbox.sandbox_path}</code></dd></div>
            <div><dt>Status</dt><dd>{sandbox.status.replaceAll("_", " ")}</dd></div>
            <div><dt>State version</dt><dd>{sandbox.state_version}</dd></div>
            <div><dt>Event sequence</dt><dd>{sandbox.event_sequence}</dd></div>
          </dl>
          {sandbox.verification ? (
            <div className={styles.verificationBlock}>
              <h4>Sandbox verification</h4>
              <pre className={styles.codeBlock}>{JSON.stringify(sandbox.verification, null, 2)}</pre>
            </div>
          ) : null}
        </div>
      ) : null}

      {/* Action buttons */}
      <div className={styles.actions}>
        <span>State version {initialState.state_version}</span>
        <div className={styles.actionButtons}>
          {!loading && (!preparation || preparation.status === "not_started") ? (
            <button
              type="button"
              className={`${styles.actionButton} ${styles.primaryButton}`}
              disabled={working !== null}
              onClick={handlePrepare}
            >
              {working === "prepare" ? "Preparing…" : "Prepare stage"}
            </button>
          ) : null}
          {!loading && preparation && !sandbox ? (
            <button
              type="button"
              className={`${styles.actionButton} ${styles.primaryButton}`}
              disabled={working !== null || !g07Approved}
              onClick={handleCreateSandbox}
            >
              {working === "sandbox" ? "Creating sandbox…" : "Create sandbox"}
            </button>
          ) : null}
          {!loading && sandbox && !sandboxReady ? (
            <button
              type="button"
              className={`${styles.actionButton} ${styles.primaryButton}`}
              disabled={working !== null}
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
