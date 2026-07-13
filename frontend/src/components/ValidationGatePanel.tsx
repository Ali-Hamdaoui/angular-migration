import type { MigrationRunDto as MigrationRun } from "@/types/generated/api";
import { StatusPill } from "./StatusPill";
import styles from "./ControlTowerShell.module.css";

export function ValidationGatePanel({ run }: { run: MigrationRun }) {
  return <section className={styles.panel}><h2>Validation gates</h2>{run.validation_gates.map((gate) => <article className={styles.row} key={gate.gate_id}><div><strong>{gate.name}</strong><p>{gate.details}</p></div><StatusPill value={gate.status} /></article>)}</section>;
}