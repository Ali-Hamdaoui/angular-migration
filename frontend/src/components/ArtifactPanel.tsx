import type { MigrationRun } from "@/types/migration";
import styles from "./ControlTowerShell.module.css";

export function ArtifactPanel({ run }: { run: MigrationRun }) {
  return <section className={styles.panel}><h2>Artifacts</h2><ul className={styles.list}>{run.artifacts.map((artifact) => <li key={artifact.artifact_id}><code>{artifact.relative_path}</code><span>{artifact.artifact_type}</span></li>)}</ul><p className={styles.note}>Artifact opening is introduced with the artifact-store API.</p></section>;
}