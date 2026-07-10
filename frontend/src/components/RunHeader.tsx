import type { MigrationRun } from "@/types/migration";
import { StatusPill } from "./StatusPill";
import styles from "./ControlTowerShell.module.css";

export function RunHeader({ run }: { run: MigrationRun }) {
  return <header className={styles.header}><div><p className={styles.kicker}>Migration run</p><h1>{run.source_angular_version} → {run.target_angular_version}</h1><p>{run.run_id}</p></div><StatusPill value={run.status} /></header>;
}