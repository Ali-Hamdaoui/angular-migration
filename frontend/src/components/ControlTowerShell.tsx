import type { MigrationRunDto as MigrationRun } from "@/types/generated/api";
import type { ConnectionStatus } from "@/hooks/useMigrationEvents";
import { AgentActivityPanel } from "./AgentActivityPanel";
import { ApprovalPanel } from "./ApprovalPanel";
import { ArtifactPanel } from "./ArtifactPanel";
import { AssistantPanel } from "./AssistantPanel";
import { BaselineValidationPanel } from "./BaselineValidationPanel";
import { DiagnosticsPanel } from "./DiagnosticsPanel";
import { LlmUsagePanel } from "./LlmUsagePanel";
import { ReportPanel } from "./ReportPanel";
import { RunHeader } from "./RunHeader";
import { StageCards } from "./StageCards";
import { ValidationGatePanel } from "./ValidationGatePanel";
import { WorkflowTimeline } from "./WorkflowTimeline";
import styles from "./ControlTowerShell.module.css";

export function ControlTowerShell({ run, runId, connectionStatus }: { run: MigrationRun; runId?: string; connectionStatus?: ConnectionStatus }) {
  const stateVersion = Math.max(1, ...run.workflow_events.map((event) => Number(event.payload.next_state_version ?? 1)));
  const matrixConnection = connectionStatus === "open" ? "open" : connectionStatus === "reconnecting" ? "reconnecting" : connectionStatus === "recovering" ? "recovering" : connectionStatus === "closed" ? "failed" : "connecting";
  return <main className={styles.shell}><RunHeader run={run} /><WorkflowTimeline run={run} /><StageCards run={run} /><div className={styles.twoColumns}><AgentActivityPanel run={run} /><ValidationGatePanel run={run} />{runId ? <BaselineValidationPanel runId={runId} stateVersion={stateVersion} connectionStatus={matrixConnection} /> : null}<ApprovalPanel run={run} /><ArtifactPanel run={run} /><AssistantPanel /><LlmUsagePanel run={run} /><DiagnosticsPanel run={run} /><ReportPanel run={run} /></div></main>;
}
