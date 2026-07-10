import type { MigrationRunDto as MigrationRun } from "@/types/generated/api";
import { StatusPill } from "./StatusPill";
import styles from "./ControlTowerShell.module.css";

export function AgentActivityPanel({ run }: { run: MigrationRun }) {
  return <section className={styles.panel}><h2>Agent activity</h2>{run.agent_executions.map((agent) => <article className={styles.row} key={agent.execution_id}><div><strong>{agent.agent_name}</strong><p>{agent.summary}</p></div><StatusPill value={agent.status} /></article>)}</section>;
}