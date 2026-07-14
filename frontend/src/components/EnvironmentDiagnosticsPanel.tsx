"use client";

import { useCallback, useEffect, useState } from "react";
import { getEnvironmentDiagnostics, refreshEnvironment } from "@/api/migrations";
import type { EnvironmentCapabilityResult, RuntimeInventoryEntry } from "@/types/generated/api";
import styles from "./EnvironmentDiagnosticsPanel.module.css";

const EMPTY = "No diagnostics yet. Refresh to inspect this machine.";

function runtimeLabel(runtime: RuntimeInventoryEntry): string {
  return runtime.version ? runtime.name + " " + runtime.version : runtime.name;
}

export function EnvironmentDiagnosticsPanel() {
  const [result, setResult] = useState<EnvironmentCapabilityResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setResult(await getEnvironmentDiagnostics());
    } catch {
      setResult(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function handleRefresh() {
    setRefreshing(true);
    setError(null);
    try {
      setResult(await refreshEnvironment({
        idempotency_key: "environment-ui-" + Date.now(),
        actor: "control-tower",
      }));
    } catch {
      setError("Environment refresh failed. Check backend connectivity and try again.");
    } finally {
      setRefreshing(false);
    }
  }

  const snapshot = result?.snapshot;
  return (
    <section className={styles.panel} aria-labelledby="environment-heading">
      <div className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Machine readiness</p>
          <h2 id="environment-heading">Environment Diagnostics</h2>
        </div>
        <button className={styles.refresh} type="button" onClick={handleRefresh} disabled={refreshing}>
          {refreshing ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {loading ? <p className={styles.note}>Loading diagnostics…</p> : null}
      {!loading && !snapshot ? <p className={styles.note}>{error ?? EMPTY}</p> : null}
      {error && snapshot ? <p className={styles.error}>{error}</p> : null}

      {snapshot ? (
        <>
          <div className={styles.status + " " + styles[snapshot.status]}>
            <strong>{snapshot.status.toUpperCase()}</strong>
            <span>{snapshot.blockers.length ? snapshot.blockers.length + " blocker(s)" : "No blockers"}</span>
          </div>
          <div className={styles.runtimeGrid}>
            {snapshot.runtimes.map((runtime) => (
              <div className={styles.card} key={runtime.name}>
                <span>{runtimeLabel(runtime)}</span>
                <small>{runtime.status + (runtime.installation_root ? " · " + runtime.installation_root : "")}</small>
              </div>
            ))}
          </div>
          <div className={styles.details}>
            <div><strong>Node/npm/npx</strong><span>{snapshot.node_npm_npx_paired ? "Paired" : "Mismatch or unavailable"}</span></div>
            <div><strong>Local storage</strong><span>{snapshot.storage.status + " · " + (snapshot.storage.writable ? "writable" : "not writable")}</span></div>
            <div><strong>Registry</strong><span>{snapshot.network.registry_configured ? "configured" : "not configured"}</span></div>
            <div><strong>Proxy / CA</strong><span>{(snapshot.network.proxy_configured || snapshot.network.https_proxy_configured ? "configured" : "not configured") + " · " + (snapshot.network.custom_ca_configured ? "CA present" : "default CA")}</span></div>
          </div>
          {snapshot.blockers.length ? <p className={styles.error}>Action required: {snapshot.blockers.join(", ")}</p> : null}
          {snapshot.warnings.length ? <p className={styles.warning}>Warnings: {snapshot.warnings.join(", ")}</p> : null}
        </>
      ) : null}
    </section>
  );
}