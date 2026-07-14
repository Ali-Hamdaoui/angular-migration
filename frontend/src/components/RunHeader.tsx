import type { MigrationRunDto as MigrationRun } from "@/types/generated/api";
import { StatusPill } from "./StatusPill";
import styles from "./ControlTowerShell.module.css";

export function RunHeader({ run }: { run: MigrationRun }) {
  return (
    <header className={styles.header}>
      <div>
        <p className={styles.kicker}>Migration run</p>
        <h1>{run.source_angular_version} → {run.target_angular_version}</h1>
        <p>{run.run_id}</p>
      </div>
      <div className={styles.dimensionGrid} aria-label="Authoritative workflow dimensions">
        <div><span>Run</span><StatusPill value={run.status} /></div>
        <div><span>Phase</span><StatusPill value={run.phase_status} /></div>
        <div><span>Approval</span><StatusPill value={run.approval_status} /></div>
        <div><span>Repair</span><StatusPill value={run.repair_status} /></div>
      </div>
    </header>
  );
}