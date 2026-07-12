import type { MigrationRunDto as MigrationRun } from "@/types/generated/api";
import { AgentActivityPanel } from "./AgentActivityPanel";
import { ApprovalPanel } from "./ApprovalPanel";
import { ArtifactPanel } from "./ArtifactPanel";
import { AssistantPanel } from "./AssistantPanel";
import { DiagnosticsPanel } from "./DiagnosticsPanel";
import { LlmUsagePanel } from "./LlmUsagePanel";
import { ReportPanel } from "./ReportPanel";
import { RunHeader } from "./RunHeader";
import { StageCards } from "./StageCards";
import { ValidationGatePanel } from "./ValidationGatePanel";
import { WorkflowTimeline } from "./WorkflowTimeline";
import styles from "./ControlTowerShell.module.css";

export function ControlTowerShell({ run }: { run: MigrationRun }) {
  return <main className={styles.shell}><RunHeader run={run} /><WorkflowTimeline run={run} /><StageCards run={run} /><div className={styles.twoColumns}><AgentActivityPanel run={run} /><ValidationGatePanel run={run} /><ApprovalPanel run={run} /><ArtifactPanel run={run} /><AssistantPanel /><LlmUsagePanel run={run} /><DiagnosticsPanel run={run} /><ReportPanel run={run} /></div></main>;
}