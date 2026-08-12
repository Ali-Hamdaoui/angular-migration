import {
  AlertCircle,
  CheckCircle2,
  CircleHelp,
  LoaderCircle,
  OctagonAlert,
  type LucideIcon,
} from "lucide-react";
import type { CurrentAction } from "@/presentation/currentAction";
import type { JourneyKey } from "@/presentation/runJourney";
import type { ControlTowerSection } from "./ControlTowerSidebar";
import styles from "./ControlTowerLayout.module.css";

const ACTION_ICONS: Record<CurrentAction["kind"], LucideIcon> = {
  gate: AlertCircle,
  blocked: OctagonAlert,
  running: LoaderCircle,
  complete: CheckCircle2,
  unavailable: CircleHelp,
};

export const ACTION_LABELS: Record<CurrentAction["kind"], string> = {
  gate: "Waiting for approval",
  blocked: "Blocked",
  running: "Running",
  complete: "Completed",
  unavailable: "State unavailable",
};

const NAVIGATION_LABELS: Record<Exclude<ControlTowerSection, "overview">, string> = {
  pipeline: "View in pipeline",
  evidence: "Open evidence",
  diagnostics: "Open diagnostics",
};

export function CurrentActionCard({
  action,
  onNavigate,
}: {
  action: CurrentAction;
  onNavigate: (section: ControlTowerSection, stageKey?: JourneyKey) => void;
}) {
  const Icon = ACTION_ICONS[action.kind];
  const refreshing = action.authority.freshness === "refreshing";
  const navigationWithheld = action.authority.navigation === "withheld";
  const navigationLabel = action.section === "overview" ? null : NAVIGATION_LABELS[action.section];

  return (
    <section
      className={styles.currentActionCard}
      data-kind={action.kind}
      aria-labelledby="current-action-title"
    >
      <div className={styles.currentActionIcon} aria-hidden="true">
        <Icon size={34} strokeWidth={2} />
      </div>
      <div className={styles.currentActionCopy}>
        <span className={styles.actionEyebrow}>{refreshing ? "Refreshing" : ACTION_LABELS[action.kind]}</span>
        <h2 id="current-action-title">{action.title}</h2>
        <p>{action.summary}</p>
        {action.consequence ? <p className={styles.actionConsequence}>{action.consequence}</p> : null}
      </div>
      {navigationWithheld ? (
        <button className={styles.actionButton} type="button" disabled>
          Waiting for authoritative refresh
        </button>
      ) : navigationLabel ? (
        <button
          className={styles.actionButton}
          type="button"
          onClick={() => onNavigate(action.section, action.stageKey)}
        >
          {navigationLabel}
        </button>
      ) : null}
    </section>
  );
}
