"use client";

import { useEffect, useState } from "react";
import { getLlmUsage } from "@/api/llm";
import { getAuthoritativeRunTiming } from "@/api/runs";
import type { AuthoritativeRunStateDto } from "@/types/generated/api";
import type { LlmUsageResponse } from "@/types/llm";
import { formatDuration, formatTimestamp } from "../MigrationTimingPanel";
import styles from "../ControlTowerShell.module.css";

type Props = {
  runId: string;
  run: AuthoritativeRunStateDto;
};

export function OperationalSummary({ runId, run }: Props) {
  const [usage, setUsage] = useState<LlmUsageResponse | null>(null);
  const [usageFailed, setUsageFailed] = useState(false);
  const [timing, setTiming] = useState<Awaited<ReturnType<typeof getAuthoritativeRunTiming>> | null>(null);
  const [timingFailed, setTimingFailed] = useState(false);

  useEffect(() => {
    let active = true;
    setUsage(null);
    setUsageFailed(false);
    setTiming(null);
    setTimingFailed(false);
    void (async () => {
      const [usageResult, timingResult] = await Promise.allSettled([getLlmUsage(runId), getAuthoritativeRunTiming(runId)]);
      if (!active) return;
      if (usageResult.status === "fulfilled") setUsage(usageResult.value);
      else setUsageFailed(true);
      if (timingResult.status === "fulfilled") setTiming(timingResult.value);
      else setTimingFailed(true);
    })();
    return () => { active = false; };
  }, [runId]);

  const elapsedLabel = timing?.total_measurement_status === "running" ? "Elapsed as of" : "Total wall-clock";

  return <section className={styles.panel} aria-labelledby="operational-summary-heading" aria-label={`Operational summary for run ${run.run_id}`}>
    <div className={styles.previewHeader}><div><p className={styles.kicker}>Backend-owned metrics</p><h2 id="operational-summary-heading">Operational summary</h2></div><span className={styles.status}>{timing ? (timing.total_measurement_status === "running" ? "Running" : "Measured") : timingFailed ? "Unavailable" : "Loading"}</span></div>
    <ul className={styles.metricList} aria-label="LLM consumption">
      <li><span>LLM calls</span><strong>{usage ? usage.llm_calls.toLocaleString() : "—"}</strong></li>
      <li><span>Total tokens</span><strong>{usage ? usage.total_tokens.toLocaleString() : "—"}</strong></li>
    </ul>
    {usageFailed ? <p className={styles.note}>LLM usage not available.</p> : !usage ? <p className={styles.note}>Loading LLM usage…</p> : null}
    <ul className={styles.metricList} aria-label="Migration timing">
      <li><span>{elapsedLabel}</span><strong>{timing ? formatDuration(timing.total_duration_seconds) : "—"}</strong></li>
      <li><span>Start</span><strong>{timing ? formatTimestamp(timing.started_at) : "—"}</strong></li>
      <li><span>Finish</span><strong>{timing ? (timing.finished_at ? formatTimestamp(timing.finished_at) : "Not finished") : "—"}</strong></li>
    </ul>
    {timingFailed ? <p className={styles.note}>Migration timing not available.</p> : null}
  </section>;
}

export default OperationalSummary;
