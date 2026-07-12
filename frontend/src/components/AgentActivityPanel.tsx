import type { MigrationRunDto as MigrationRun } from "@/types/generated/api";
import { StatusPill } from "./StatusPill";
import styles from "./ControlTowerShell.module.css";

export function AgentActivityPanel({ run }: { run: MigrationRun }) {
  return (
    <section className={styles.panel}>
      <h2>Execution activity</h2>
      <div className={styles.activityGroup}>
        <h3>Deterministic components</h3>
        {run.component_executions.map((component) => (
          <article className={styles.row} key={component.execution_id}>
            <div>
              <strong>{component.component_name}</strong>
              <p>{component.summary}</p>
            </div>
            <StatusPill value={component.status} />
          </article>
        ))}
      </div>
      <div className={styles.activityGroup}>
        <h3>AI-assisted agents</h3>
        {run.agent_executions.map((agent) => (
          <article className={styles.row} key={agent.execution_id}>
            <div>
              <strong>{agent.agent_name}</strong>
              <p>{agent.summary}</p>
            </div>
            <StatusPill value={agent.status} />
          </article>
        ))}
      </div>
    </section>
  );
}