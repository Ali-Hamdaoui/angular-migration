import { FileText, FolderSearch } from "lucide-react";
import type { AuthoritativeRunStateDto } from "@/types/generated/api";
import type { TransformationProjection } from "@/types/transformation";
import type { ArtifactPresentation } from "@/presentation/artifacts";
import type { RunWorkspaceProjection } from "@/presentation/currentAction";
import type { JourneyKey, TransformationLoadStatus } from "@/presentation/runJourney";
import type { ControlTowerSection } from "./ControlTowerSidebar";
import { CurrentActionCard } from "./CurrentActionCard";
import { OperationalSummarySlot } from "./OperationalSummarySlot";
import { RunJourneyStrip } from "./RunJourneyStrip";
import { TechnicalDetails } from "./TechnicalDetails";
import styles from "./ControlTowerLayout.module.css";

function countLabel(count: number, singular: string) {
  return `${count} ${count === 1 ? singular : `${singular}s`}`;
}

export function OperatorOverview({
  projection,
  run,
  transformation,
  transformationStatus,
  artifacts,
  onNavigate,
  error = null,
}: {
  projection: RunWorkspaceProjection;
  run: AuthoritativeRunStateDto;
  transformation: TransformationProjection | null;
  transformationStatus: TransformationLoadStatus;
  artifacts: ArtifactPresentation[];
  onNavigate: (section: ControlTowerSection, stageKey?: JourneyKey) => void;
  error?: string | null;
}) {
  return (
    <section className={styles.operatorOverview} aria-labelledby="overview-heading">
      <h2 className={styles.visuallyHidden} id="overview-heading">Overview</h2>
      {error ? <p className={styles.overviewAlert} role="alert">{error}</p> : null}
      <CurrentActionCard action={projection.currentAction} onNavigate={onNavigate} />
      <RunJourneyStrip journey={projection.journey} />
      <OperationalSummarySlot runId={run.run_id} run={run} />

      <section className={styles.journeyStory} aria-labelledby="journey-story-title">
        <h2 className={styles.visuallyHidden} id="journey-story-title">Completed and next</h2>
        <ol>
          <li data-story="completed"><span>Completed</span><strong>{projection.completed}</strong></li>
          <li data-story="next"><span>Next</span><strong>{projection.next}</strong></li>
        </ol>
      </section>

      <section className={styles.evidenceGlance} aria-labelledby="evidence-glance-title">
        <div className={styles.sectionTitleRow}>
          <div>
            <FileText aria-hidden="true" size={24} />
            <div>
              <h2 id="evidence-glance-title">Evidence at a glance</h2>
              <p>Backend-registered proof supporting this migration run.</p>
            </div>
          </div>
          {artifacts.length ? (
            <button type="button" onClick={() => onNavigate("evidence")}>
              <FolderSearch aria-hidden="true" size={18} />
              Open evidence
            </button>
          ) : null}
        </div>
        {artifacts.length ? (
          <ul className={styles.evidenceList}>
            {artifacts.slice(0, 3).map((presentation) => (
              <li key={presentation.artifact.artifact_id}>
                <strong>{presentation.title}</strong>
                <span>{presentation.stageLabel} · {presentation.category}</span>
              </li>
            ))}
          </ul>
        ) : <p className={styles.emptyState}>Evidence not available.</p>}
      </section>

      <TechnicalDetails title="Technical details">
        <dl className={styles.technicalGrid}>
          <div><dt>Run ID</dt><dd><code>{run.run_id}</code></dd></div>
          <div><dt>Run status</dt><dd><code>{run.status}</code></dd></div>
          <div><dt>Run phase</dt><dd><code>{run.run_phase}</code></dd></div>
          <div><dt>Phase status</dt><dd><code>{run.phase_status}</code></dd></div>
          <div><dt>Approval status</dt><dd><code>{run.approval_status}</code></dd></div>
          <div><dt>Run state version</dt><dd><code>{run.state_version}</code></dd></div>
          <div><dt>Event count</dt><dd>{countLabel(run.workflow_events.length, "event")}</dd></div>
          <div><dt>Artifact count</dt><dd>{countLabel(run.artifacts.length, "artifact")}</dd></div>
          <div><dt>Transformation loading</dt><dd><code>{transformationStatus}</code></dd></div>
          <div><dt>Transformation ID</dt><dd><code>{transformation?.continuation_id ?? "Not available"}</code></dd></div>
          <div><dt>Transformation state version</dt><dd><code>{transformation?.state_version ?? "Not available"}</code></dd></div>
          <div><dt>Current-action source</dt><dd><code>{projection.currentAction.rawSource}</code></dd></div>
          <div className={styles.technicalWide}><dt>Raw event types</dt><dd><code>{run.workflow_events.map((event) => event.event_type).join(", ") || "None recorded"}</code></dd></div>
          <div className={styles.technicalWide}><dt>Artifact checksums</dt><dd><code>{run.artifacts.map((artifact) => artifact.checksum).join(", ") || "None registered"}</code></dd></div>
        </dl>
      </TechnicalDetails>
    </section>
  );
}
