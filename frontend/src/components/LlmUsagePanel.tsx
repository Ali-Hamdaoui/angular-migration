import type { MigrationRunDto as MigrationRun } from "@/types/generated/api";
import styles from "./ControlTowerShell.module.css";

export function LlmUsagePanel({ run }: { run: MigrationRun }) {
  const stateVersion = Math.max(1, ...run.workflow_events.map((event) => Number(event.payload.next_state_version ?? 1)));
  const totals = run.llm_usage.reduce(
    (acc, usage) => ({
      inputTokens: acc.inputTokens + usage.input_tokens,
      outputTokens: acc.outputTokens + usage.output_tokens,
      totalTokens: acc.totalTokens + usage.total_tokens,
      totalCost: acc.totalCost + usage.cost_usd,
    }),
    { inputTokens: 0, outputTokens: 0, totalTokens: 0, totalCost: 0 },
  );

  return (<>
    <section className={styles.panel}>
      <h2>LLM usage</h2>
      <ul className={styles.metricList}>
        <li><span>Input tokens</span><strong>{totals.inputTokens.toLocaleString()}</strong></li>
        <li><span>Output tokens</span><strong>{totals.outputTokens.toLocaleString()}</strong></li>
        <li><span>Total tokens</span><strong>{totals.totalTokens.toLocaleString()}</strong></li>
        <li><span>Estimated cost</span><strong>${totals.totalCost.toFixed(6)}</strong></li>
      </ul>
    </section>
    <LlmDiagnosticsPanel runId={run.run_id} stateVersion={stateVersion} workflowEvents={run.workflow_events} />
    </>
  );
}
import { LlmDiagnosticsPanel } from './LlmDiagnosticsPanel';
