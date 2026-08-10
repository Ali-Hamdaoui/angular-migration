"use client";

import { useEffect, useState } from "react";
import { getAuthoritativeRunTiming } from "@/api/runs";
import type { RunTimingActivityDto, RunTimingDto, TimingActivityDto, TimingSpanDto } from "@/types/generated/api";
import styles from "./ControlTowerShell.module.css";

const activityLabels: Array<[keyof RunTimingActivityDto, string]> = [
  ["llm", "Measured LLM execution"],
  ["commands", "Command activity"],
  ["human_approval_wait", "Human approval wait"],
  ["repair", "Repair activity"],
  ["validation", "Validation command activity"],
  ["sealing", "Sealing activity"],
];

export function formatDuration(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds) || seconds < 0) return "—";
  const rounded = Math.round(seconds);
  const hours = Math.floor(rounded / 3600);
  const minutes = Math.floor((rounded % 3600) / 60);
  const remaining = rounded % 60;
  if (hours > 0) return `${hours}h ${String(minutes).padStart(2, "0")}m ${String(remaining).padStart(2, "0")}s`;
  if (minutes > 0) return `${minutes}m ${String(remaining).padStart(2, "0")}s`;
  return `${remaining}s`;
}

export function formatTimestamp(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "—";
}

function statusLabel(status: TimingActivityDto["measurement_status"]): string {
  return status === "complete" ? "Measured" : status === "partial" ? "Partial" : "Unavailable";
}

function totalStatusLabel(status: RunTimingDto["total_measurement_status"]): string {
  return status === "running" ? "Running" : status === "complete" ? "Measured" : "Unavailable";
}

function activityDetail(activity: TimingActivityDto): string {
  const details = [`${activity.measured_count} measured`];
  if (activity.unmeasured_count > 0) details.push(`${activity.unmeasured_count} invocation(s) lack timing`);
  if (activity.active_count > 0) details.push(`${activity.active_count} active`);
  return details.join(" · ");
}

function SpanList({ title, spans }: { title: string; spans: TimingSpanDto[] }) {
  return <section className={styles.activityGroup} aria-labelledby={`${title.toLowerCase().replaceAll(" ", "-")}-heading`}>
    <h3 id={`${title.toLowerCase().replaceAll(" ", "-")}-heading`}>{title}</h3>
    {spans.length === 0 ? <p className={styles.note}>—</p> : <ul className={styles.metricList}>
      {spans.map((span) => {
        const status = span.status === "running" ? "Running" : span.status === "unavailable" ? "Unavailable" : null;
        return <li key={span.key}>
          <span>{span.label}</span>
          <strong>{span.status === "not_started" ? "Not started." : formatDuration(span.duration_seconds)}{status && <small>{status}</small>}</strong>
        </li>;
      })}
    </ul>}
  </section>;
}

export function MigrationTimingPanel({ runId, refreshKey = 0 }: { runId: string; refreshKey?: number }) {
  const [timing, setTiming] = useState<RunTimingDto | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    setError(false);
    void (async () => {
      try {
        const next = await getAuthoritativeRunTiming(runId);
        if (!next) throw new Error("Timing response unavailable");
        if (active) setTiming(next);
      } catch {
        if (active) setError(true);
      }
    })();
    return () => { active = false; };
  }, [runId, refreshKey]);

  if (error) return <section className={styles.panel} role="alert"><h2>Migration timing is temporarily unavailable</h2><p className={styles.note}>Refresh to retry this panel.</p></section>;
  if (!timing) return <section className={styles.panel} aria-busy="true"><h2>Migration timing</h2><p className={styles.note}>{"Loading authoritative timing\u2026"}</p></section>;

  const totalLabel = timing.total_measurement_status === "running" ? "Elapsed as of" : "Total wall-clock";
  return <section className={styles.panel} aria-labelledby="migration-timing-heading">
    <div className={styles.previewHeader}><div><span className={styles.kicker}>Backend-owned timing</span><h2 id="migration-timing-heading">Migration timing</h2></div><span className={styles.status}>{totalStatusLabel(timing.total_measurement_status)}</span></div>
    <div className={styles.metricGrid}>
      <strong>{formatDuration(timing.total_duration_seconds)}<small>{totalLabel}</small></strong>
      <strong>{formatTimestamp(timing.started_at)}<small>Start</small></strong>
      <strong>{formatTimestamp(timing.finished_at ?? timing.as_of)}<small>{timing.finished_at ? "Finish" : "As of"}</small></strong>
    </div>
    <p className={styles.note}>{"Cumulative activity \u2014 categories may overlap."}</p>
    <div className={styles.twoColumns}>
      <section aria-labelledby="timing-activity-heading"><h3 id="timing-activity-heading">Cumulative activity</h3><ul className={styles.metricList}>
        {activityLabels.map(([key, label]) => { const activity = timing.activity[key]; return <li key={key}><span>{label}<small>{activityDetail(activity)}</small></span><strong>{formatDuration(activity.duration_seconds)}<small>{statusLabel(activity.measurement_status)}</small></strong></li>; })}
      </ul></section>
      <section aria-labelledby="timing-spans-heading"><h3 id="timing-spans-heading">Workflow spans</h3><SpanList title="Major phases" spans={timing.phases} /><SpanList title="Route stages" spans={timing.stages} /></section>
    </div>
  </section>;
}
