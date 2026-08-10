import { useState } from "react";
import type { MigrationRunDto as MigrationRun } from "@/types/generated/api";
import type { ConnectionStatus } from "@/hooks/useMigrationEvents";
import { AgentActivityPanel } from "./AgentActivityPanel";
import { ApprovalPanel } from "./ApprovalPanel";
import { ArtifactPanel } from "./ArtifactPanel";
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

type ShellSection = "overview" | "pipeline" | "evidence" | "diagnostics";

export function ControlTowerShell({ run, runId, connectionStatus, mode = "authoritative" }: { run: MigrationRun; runId?: string; connectionStatus?: ConnectionStatus; mode?: "authoritative" | "mock" }) {
  const [activeSection, setActiveSection] = useState<ShellSection>("overview");
  const stateVersion = Math.max(1, ...run.workflow_events.map((event) => Number(event.payload.next_state_version ?? 1)));
  const matrixConnection = connectionStatus === "open" ? "open" : connectionStatus === "reconnecting" ? "reconnecting" : connectionStatus === "recovering" ? "recovering" : connectionStatus === "closed" ? "failed" : "connecting";
  return <main className={styles.shell}><div className={styles.content}>
    <nav className={styles.legacyNav} aria-label="Run sections">
      {(["overview", "pipeline", "evidence", "diagnostics"] as const).map((section) => (
        <a key={section} href={`#${section}`} className={activeSection === section ? styles.legacyNavActive : undefined} aria-current={activeSection === section ? "page" : undefined} onClick={() => setActiveSection(section)}>
          {section[0].toUpperCase() + section.slice(1)}
        </a>
      ))}
    </nav>
    <section id="overview"><RunHeader run={run} /><WorkflowTimeline run={run} /></section>
    <section id="pipeline"><StageCards run={run} /></section>
    <section id="evidence"><div className={styles.dashboardGrid}><div className={styles.primaryColumn}><ArtifactPanel run={run} /><ReportPanel run={run} /></div></div></section>
    <section id="diagnostics"><div className={styles.dashboardGrid}><div className={styles.primaryColumn}><AgentActivityPanel run={run} />{mode !== "mock" && runId ? <BaselineValidationPanel runId={runId} stateVersion={stateVersion} connectionStatus={matrixConnection} /> : null}{mode !== "mock" && runId ? <BaselineQualificationPanel runId={runId} stateVersion={stateVersion} /> : null}</div><aside className={styles.secondaryColumn}>{mode === "mock" ? <p className={styles.note} role="note">Demo controls are unavailable because this run is not authoritative.</p> : <><ValidationGatePanel run={run} /><ApprovalPanel run={run} /><DiagnosticsPanel run={run} /><LlmUsagePanel run={run} /></>}</aside></div></section>
  </div></main>;
}
