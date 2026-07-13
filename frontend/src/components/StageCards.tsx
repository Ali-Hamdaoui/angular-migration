import type { MigrationRunDto as MigrationRun } from "@/types/generated/api";
import styles from "./ControlTowerShell.module.css";
import { StatusPill } from "./StatusPill";

export function StageCards({ run }: { run: MigrationRun }) {
  return <section><h2>Stages</h2><div className={styles.cardGrid}>{run.stages.map((stage) => <article className={styles.card} key={stage.stage_id}><p className={styles.kicker}>Stage {stage.stage_order}</p><h3>Angular {stage.source_angular_version} → {stage.target_angular_version}</h3><StatusPill value={stage.status} /></article>)}</div></section>;
}
