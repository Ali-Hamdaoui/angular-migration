"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiClientError } from "@/api/client";
import { authorizeBaselineInstall, createBaselineWorkspace, getBaseline, prequalifyBaseline } from "@/api/baseline";
import type { AuthoritativeRunStateDto, BaselineResponse } from "@/types/generated/api";
import styles from "./ControlTowerShell.module.css";

function nextKey(runId: string, operation: string) {
  return `baseline-${operation}-${runId}-${Date.now()}`;
}

export function BaselinePreparationPanel({ runId, initialState }: { runId: string; initialState: AuthoritativeRunStateDto }) {
  const [baseline, setBaseline] = useState<BaselineResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);

  const refresh = useCallback(() => {
    setLoading(true);
    setError(null);
    getBaseline(runId)
      .then(setBaseline)
      .catch((reason: unknown) => {
        if (reason instanceof ApiClientError && reason.status === 404) setBaseline(null);
        else setError("Baseline evidence could not be loaded.");
      })
      .finally(() => setLoading(false));
  }, [runId]);

  useEffect(() => { refresh(); }, [refresh]);

  async function act(operation: "workspace" | "prequalify" | "authorize" | "reject") {
    setWorking(operation); setError(null); setStale(false);
    try {
      const request = { expected_state_version: initialState.state_version, idempotency_key: nextKey(runId, operation), actor: "control-tower" };
      const result = operation === "workspace"
        ? await createBaselineWorkspace(runId, request)
        : operation === "prequalify"
          ? await prequalifyBaseline(runId, request)
          : await authorizeBaselineInstall(runId, { ...request, decision: operation === "authorize" ? "authorize" : "reject" });
      setBaseline(result);
    } catch (reason: unknown) {
      if (reason instanceof ApiClientError && reason.status === 409) setStale(true);
      else setError("The baseline action could not be completed.");
    } finally { setWorking(null); }
  }

  const status = baseline?.status ?? "not_started";
  const blocked = Boolean(baseline?.blockers.length);
  return (
    <section className={styles.panel} aria-labelledby="baseline-preparation-title">
      <div className={styles.header}>
        <div><p className={styles.kicker}>S1-F10 baseline boundary</p><h2 id="baseline-preparation-title">Baseline sandbox and package safety</h2><p className={styles.note}>The backend owns the sandbox path, fingerprints, package metadata, and install decision.</p></div>
        <span className={styles.status}>{status.replaceAll("_", " ")}</span>
      </div>
      {loading ? <p role="status">Loading baseline evidence…</p> : null}
      {error ? <p role="alert">{error}</p> : null}
      {stale ? <p role="alert">This run changed while the action was submitted. Refreshing authoritative evidence is required.</p> : null}
      {!loading && !baseline && !error ? <p className={styles.note}>No baseline sandbox has been created.</p> : null}
      {baseline ? <>
        <dl className={styles.metadataGrid}>
          <div><dt>Sandbox</dt><dd><code>{baseline.sandbox_path}</code></dd></div>
          <div><dt>Input fingerprint</dt><dd><code>{baseline.input_fingerprint}</code></dd></div>
          <div><dt>Sandbox fingerprint</dt><dd><code>{baseline.sandbox_fingerprint ?? "pending"}</code></dd></div>
          <div><dt>Authorization</dt><dd>{baseline.authorization_status.replaceAll("_", " ")}</dd></div>
        </dl>
        {baseline.blockers.length ? <div role="alert"><h3>Blocked</h3><ul>{baseline.blockers.map((item) => <li key={item}><code>{item}</code></li>)}</ul></div> : null}
        {baseline.warnings.length ? <div><h3>Review notes</h3><ul>{baseline.warnings.map((item) => <li key={item}><code>{item}</code></li>)}</ul></div> : null}
        <div className={styles.cardGrid}>
          <div className={styles.card}><strong>Dependencies</strong><p>{baseline.sources.length} sources inventoried</p></div>
          <div className={styles.card}><strong>Lifecycle scripts</strong><p>{baseline.scripts.length} scripts audited</p></div>
          <div className={styles.card}><strong>Artifacts</strong><p>{baseline.artifact_ids.length} immutable evidence artifacts</p></div>
        </div>
        <p className={styles.note}>Evidence checksum: <code>{baseline.checksum}</code></p>
      </> : null}
      <div className={styles.row}>
        <span>State version {initialState.state_version}</span>
        <span>
          {!baseline ? <button disabled={working !== null} onClick={() => act("workspace")}>{working === "workspace" ? "Creating…" : "Create baseline sandbox"}</button> : null}
          {baseline?.status === "workspace_ready" ? <button disabled={working !== null} onClick={() => act("prequalify")}>{working === "prequalify" ? "Prequalifying…" : "Prequalify package"}</button> : null}
          {baseline?.status === "requires_review" ? <><button disabled={working !== null || blocked} onClick={() => act("authorize")}>{working === "authorize" ? "Authorizing…" : "Authorize install"}</button><button disabled={working !== null} onClick={() => act("reject")}>Reject</button></> : null}
        </span>
      </div>
    </section>
  );
}
