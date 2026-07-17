import type { MigrationRunDto as MigrationRun } from "@/types/generated/api";
import type { ConnectionStatus } from "@/hooks/useMigrationEvents";
import { AgentActivityPanel } from "./AgentActivityPanel";
import { ApprovalPanel } from "./ApprovalPanel";
import { ArtifactPanel } from "./ArtifactPanel";
import { AssistantPanel } from "./AssistantPanel";
import { BaselineValidationPanel } from "./BaselineValidationPanel";
import { BaselineQualificationPanel } from "./BaselineQualificationPanel";
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
  return <main className={styles.shell}><div className={styles.content}><RunHeader run={run} /><WorkflowTimeline run={run} /><StageCards run={run} /><div className={styles.dashboardGrid}><div className={styles.primaryColumn}><AgentActivityPanel run={run} />{runId ? <><BaselineValidationPanel runId={runId} stateVersion={stateVersion} connectionStatus={matrixConnection} /><BaselineQualificationPanel runId={runId} stateVersion={stateVersion} /></> : null}<ArtifactPanel run={run} /><ReportPanel run={run} /></div><aside className={styles.secondaryColumn}><ValidationGatePanel run={run} /><ApprovalPanel run={run} /><DiagnosticsPanel run={run} /><LlmUsagePanel run={run} /><AssistantPanel /></aside></div></div></main>;
}
