import { getBackendBaseUrl } from "@/api/client";
import type { MigrationRunDto as MigrationRun } from "@/types/generated/api";
import styles from "./ControlTowerShell.module.css";

export function ArtifactPanel({ run }: { run: MigrationRun }) {
  const backendBaseUrl = getBackendBaseUrl();

  return (
    <section className={styles.panel}>
      <h2>Artifacts</h2>
      <ul className={styles.list}>
        {run.artifacts.map((artifact) => (
          <li key={artifact.artifact_id}>
            <code>{artifact.relative_path}</code>
            <span>{artifact.artifact_type}</span>
            <a className={styles.actionLink} href={`${backendBaseUrl}/artifacts/${artifact.artifact_id}`}>
              Open
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}
