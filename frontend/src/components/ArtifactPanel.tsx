import type { MigrationRunDto as MigrationRun } from "@/types/generated/api";
import { ArtifactPreviewPanel } from "./ArtifactPreviewPanel";
import styles from "./ControlTowerShell.module.css";

export function ArtifactPanel({ run }: { run: MigrationRun }) {
  return (
    <section className={styles.panel}>
      <h2>Artifacts</h2>
      <div className={styles.previewList}>
        {run.artifacts.map((artifact) => (
          <ArtifactPreviewPanel artifact={artifact} key={artifact.artifact_id} />
        ))}
      </div>
    </section>
  );
}
