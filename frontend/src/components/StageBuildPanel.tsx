"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiClientError } from "@/api/client";
import { cancelStageBuild, getStageBuildMatrix, startStageBuild } from "@/api/stageBuild";
import type { StageBuildResult, StageBuildTarget } from "@/types/stageBuild";
import styles from "./ControlTowerShell.module.css";

type ConnectionStatus = "loading" | "connecting" | "open" | "reconnecting" | "recovering" | "failed";

const terminal = new Set(["passed", "failed", "blocked", "not_configured", "cancelled", "skipped_not_applicable"]);
const targetKindLabels: Record<string, string> = {
  build: "Build", prod_build: "Prod build", ssr_build: "SSR build", conditional: "Conditional",
};

function statusLabel(value: string) { return value.replaceAll("_", " "); }
function resultFor(results: StageBuildResult[], targetId: string) { return results.find((r) => r.target_id === targetId); }

export function StageBuildPanel({
  runId, stageId, stateVersion, connectionStatus,
}: {
  runId: string; stageId: string; stateVersion: number; connectionStatus: ConnectionStatus;
}) {
  const [build, setBuild] = useState<{ targets: StageBuildTarget[]; results: StageBuildResult[]; status: string; build_id: string; artifact_ids: string[]; artifact_checksums: Record<string, string>; state_version: number; event_sequence: number; idempotent_replay: boolean; } | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const [selectedTarget, setSelectedTarget] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const result = await getStageBuildMatrix(runId, stageId);
      setBuild(result);
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 404) {
        setBuild(null);
      } else {
        setError("Stage build matrix could not be loaded.");
      }
    } finally { setLoading(false); }
  }, [runId, stageId]);

  useEffect(() => { void refresh(); }, [refresh, stateVersion]);
  useEffect(() => {
    if (build?.status !== "running") return;
    const timer = window.setInterval(() => void refresh(), 1000);
    return () => window.clearInterval(timer);
  }, [refresh, build?.status]);

  async function handleStart() {
    setWorking(true); setError(null); setStale(false);
    try {
      const result = await startStageBuild(runId, stageId, {
        expected_state_version: stateVersion,
        idempotency_key: `stage-build-${runId}-${stageId}-${Date.now()}`,
        actor: "control-tower",
      });
      setBuild(result);
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 409) setStale(true);
      else setError("The stage build could not be started.");
    } finally { setWorking(false); }
  }

  async function handleCancel() {
    setWorking(true); setError(null);
    try { const result = await cancelStageBuild(runId, stageId); setBuild(result); }
    catch { setError("The build cancellation request could not be completed."); }
    finally { setWorking(false); }
  }

  const connectionLabel = useMemo(() => (
    connectionStatus === "open" ? "Live build matrix state"
    : connectionStatus === "reconnecting" ? "Connection lost. Reconnecting..."
    : connectionStatus === "recovering" ? "Refreshing authoritative build state..."
    : connectionStatus === "failed" ? "Unable to refresh build state"
    : "Connecting to build events..."
  ), [connectionStatus]);

  const targetsByProject = useMemo(() => {
    if (!build) return [];
    const map = new Map<string, StageBuildTarget[]>();
    for (const t of build.targets) {
      const key = t.project ?? "(root)";
      const list = map.get(key) ?? [];
      list.push(t);
      map.set(key, list);
    }
    return Array.from(map.entries());
  }, [build]);

  return (
    <section className={styles.panel} aria-labelledby="stage-build-title">
      <div className={styles.header}>
        <div>
          <p className={styles.kicker}>S3-F11</p>
          <h2 id="stage-build-title">Stage build matrix</h2>
          <p className={styles.note}>
            Run and inspect the required build targets — production, SSR, and conditionals.
          </p>
        </div>
        <span className={styles.status}>{build ? statusLabel(build.status) : "not loaded"}</span>
      </div>
      <div className={styles.connectionBar} role="status" aria-live="polite">{connectionLabel}</div>

      {loading && <p role="status">Loading build matrix...</p>}
      {error && <p role="alert">{error}</p>}
      {stale && <p role="alert">The run state changed while the build was requested. Refresh before retrying.</p>}

      {!loading && !build && (
        <p className={styles.note}>No build matrix has been started yet.</p>
      )}

      {build && (
        <>
          <div className={styles.previewPanel}>
            <div className={styles.previewHeader}>
              <h3>Build targets</h3>
              {build.status === "running" ? (
                <button type="button" onClick={handleCancel} disabled={working}>
                  {working ? "Cancelling..." : "Cancel"}
                </button>
              ) : terminal.has(build.status) ? (
                <button type="button" onClick={handleStart} disabled={working}>
                  {working ? "Starting..." : "Re-run"}
                </button>
              ) : (
                <button type="button" onClick={handleStart} disabled={working}>
                  {working ? "Starting..." : "Run build matrix"}
                </button>
              )}
            </div>

            {targetsByProject.length === 0 ? (
              <p className={styles.note}>No build targets configured.</p>
            ) : (
              <ul className={styles.list}>
                {targetsByProject.map(([project, targets]) => (
                  <li key={project}>
                    <strong>{project}</strong>
                    <ul>
                      {targets.map((target) => {
                        const result = resultFor(build.results ?? [], target.target_id);
                        const status = result?.status ?? (target.supported ? "pending" : target.blocker === "NOT_CONFIGURED" ? "not_configured" : "blocked");
                        return (
                          <li key={target.target_id}>
                            <code>{target.target_id}</code>
                            <span>{targetKindLabels[target.kind] ?? target.kind}</span>
                            {target.mandatory ? <strong className={styles.warning ?? ""}>Mandatory</strong> : <small>Conditional</small>}
                            <strong>{statusLabel(status)}</strong>
                            {result && (
                              <small>
                                {result.duration_ms ?? 0} ms · {result.warnings.length} warnings · {result.errors.length} errors
                              </small>
                            )}
                            {result && result.errors.length > 0 && (
                              <button type="button" onClick={() => setSelectedTarget(selectedTarget === target.target_id ? null : target.target_id)}>
                                {selectedTarget === target.target_id ? "Hide details" : "Details"}
                              </button>
                            )}
                            {selectedTarget === target.target_id && result && (
                              <ul>
                                {result.errors.map((err, i) => <li key={i} className={styles.error ?? ""}>{err}</li>)}
                                {result.warnings.map((w, i) => <li key={i} className={styles.warning ?? ""}>{w}</li>)}
                              </ul>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {build.artifact_ids.length > 0 && (
            <div className={styles.previewPanel}>
              <div className={styles.previewHeader}><h4>Evidence artifacts</h4></div>
              <ul className={styles.list}>
                {build.artifact_ids.map((id) => (
                  <li key={id}>
                    <code>{id}</code>
                    {build.artifact_checksums[id] && <small>· {build.artifact_checksums[id]}</small>}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <p className={styles.note}>
            state version {build.state_version} · event sequence {build.event_sequence}
            {build.idempotent_replay ? " · idempotent replay" : ""}
          </p>
        </>
      )}
    </section>
  );
}
