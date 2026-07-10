import type { MigrationRunDto as MigrationRun } from "@/types/generated/api";
import styles from "./ControlTowerShell.module.css";

export function ReportPanel({ run }: { run: MigrationRun }) {
  return <section className={styles.panel}><h2>Report</h2><p>Current run status: <strong>{run.status}</strong></p><p>Mock report and diff viewers are scheduled for AMF-S0-15.</p></section>;
}