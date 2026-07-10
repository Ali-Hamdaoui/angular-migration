import type { MigrationRun } from "@/types/migration";
import { StatusPill } from "./StatusPill";
import styles from "./ControlTowerShell.module.css";

export function ApprovalPanel({ run }: { run: MigrationRun }) {
  return <section className={styles.panel}><h2>Approval</h2>{run.approval_events.map((approval) => <article className={styles.row} key={approval.approval_id}><div><strong>Backend approval record</strong><p>{approval.rationale}</p></div><StatusPill value={approval.decision} /></article>)}<p className={styles.note}>Approval actions are intentionally unavailable until a backend API is implemented.</p></section>;
}