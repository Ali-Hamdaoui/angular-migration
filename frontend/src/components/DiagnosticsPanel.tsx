import type { DiagnosticsSummaryDto, MigrationRunDto as MigrationRun } from "@/types/generated/api";
import styles from "./ControlTowerShell.module.css";

const DISPLAY_METRICS = [
  "command.count",
  "artifact.count",
  "sse.event.count",
  "sse.reconnect.count",
  "llm.call.count",
  "llm.cost.total",
  "manual_item.count",
  "repair_attempt.count"
];

function formatMetric(metric: DiagnosticsSummaryDto["metrics"][number]): string {
  if (metric.unit === "usd") return `$${metric.value.toFixed(6)}`;
  return `${metric.value} ${metric.unit}`;
}

export function DiagnosticsPanel({ run }: { run: MigrationRun }) {
  const diagnostics = run.diagnostics;
  const metrics = diagnostics?.metrics.filter((metric) => DISPLAY_METRICS.includes(metric.metric_name)) ?? [];

  return (
    <section className={styles.panel}>
      <h2>Diagnostics</h2>
      <ul className={styles.metricList}>
        {metrics.map((metric) => (
          <li key={metric.metric_name}>
            <span>{metric.metric_name}</span>
            <strong>{formatMetric(metric)}</strong>
          </li>
        ))}
      </ul>
      {diagnostics?.alerts.length ? <p className={styles.note}>{diagnostics.alerts.length} alert events require review.</p> : <p className={styles.note}>No mock alert events.</p>}
      {diagnostics?.notes.map((note) => <p className={styles.note} key={note}>{note}</p>)}
    </section>
  );
}