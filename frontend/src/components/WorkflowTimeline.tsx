import type { MigrationRunDto as MigrationRun } from "@/types/generated/api";
import styles from "./ControlTowerShell.module.css";
import { StatusPill } from "./StatusPill";

export function WorkflowTimeline({ run }: { run: MigrationRun }) {
  return <section className={styles.panel}><h2>Workflow timeline</h2><ol className={styles.timeline}>{run.stages.map((stage) => <li key={stage.stage_id}><strong>{stage.stage_order}. Angular {stage.source_angular_version} → {stage.target_angular_version}</strong><StatusPill value={stage.status} /></li>)}</ol></section>;
}
