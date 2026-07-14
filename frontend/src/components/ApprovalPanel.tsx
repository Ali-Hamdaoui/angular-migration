import type { MigrationRunDto as MigrationRun } from "@/types/generated/api";
import { StatusPill } from "./StatusPill";
import styles from "./ControlTowerShell.module.css";

export function ApprovalPanel({ run }: { run: MigrationRun }) {
  return (
    <section className={styles.panel}>
      <h2>Approval and repair</h2>
      <div className={styles.row}><strong>Approval status</strong><StatusPill value={run.approval_status} /></div>
      <div className={styles.row}><strong>Repair status</strong><StatusPill value={run.repair_status} /></div>
      {run.approval_events.map((approval) => (
        <article className={styles.row} key={approval.approval_id}>
          <div><strong>Backend approval record</strong><p>{approval.rationale}</p></div>
          <StatusPill value={approval.decision} />
        </article>
      ))}
      <p className={styles.note}>Approval decisions are recorded by the backend. Production auto-approval is unavailable.</p>
    </section>
  );
}