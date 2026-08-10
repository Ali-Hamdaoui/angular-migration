import {
  AlertCircle,
  CheckCircle2,
  Circle,
  CircleDot,
  OctagonAlert,
  type LucideIcon,
} from "lucide-react";
import type { JourneyMilestone, JourneyState } from "@/presentation/runJourney";
import styles from "./ControlTowerLayout.module.css";

type JourneyWindowPosition = "previous" | "current" | "next";

interface JourneyWindowItem {
  milestone: JourneyMilestone;
  position: JourneyWindowPosition;
}

const STATE_LABELS: Record<JourneyState, string> = {
  complete: "Completed",
  current: "Running",
  "action-required": "Waiting for approval",
  blocked: "Blocked",
  "not-reached": "Not started",
  unavailable: "Not available",
};

const STATE_ICONS: Record<JourneyState, LucideIcon> = {
  complete: CheckCircle2,
  current: CircleDot,
  "action-required": AlertCircle,
  blocked: OctagonAlert,
  "not-reached": Circle,
  unavailable: Circle,
};

const WINDOW_LABELS: Record<JourneyWindowPosition, string> = {
  previous: "Previous",
  current: "Current",
  next: "Next",
};

function journeyWindow(journey: JourneyMilestone[]): JourneyWindowItem[] {
  if (journey.length === 0) return [];
  const activeIndex = journey.findIndex((milestone) =>
    milestone.state === "action-required" || milestone.state === "blocked" || milestone.state === "current",
  );
  const nextIndex = journey.findIndex((milestone) => milestone.state === "not-reached" || milestone.state === "unavailable");
  const currentIndex = activeIndex >= 0 ? activeIndex : nextIndex >= 0 ? nextIndex : journey.length - 1;
  return [
    currentIndex > 0 ? { milestone: journey[currentIndex - 1], position: "previous" as const } : null,
    { milestone: journey[currentIndex], position: "current" as const },
    currentIndex < journey.length - 1 ? { milestone: journey[currentIndex + 1], position: "next" as const } : null,
  ].filter((item): item is JourneyWindowItem => item != null);
}

function MilestoneItem({
  milestone,
  position,
}: {
  milestone: JourneyMilestone;
  position?: JourneyWindowPosition;
}) {
  const Icon = STATE_ICONS[milestone.state];
  const stateLabel = STATE_LABELS[milestone.state];
  const positionLabel = position ? WINDOW_LABELS[position] : null;
  return (
    <li
      aria-label={`${positionLabel ? `${positionLabel}: ` : ""}${milestone.label}: ${stateLabel}`}
      className={styles.journeyMilestone}
      data-position={position}
      data-state={milestone.state}
    >
      <span className={styles.journeyMarker}>
        <Icon aria-hidden="true" size={22} strokeWidth={2} />
      </span>
      <span className={styles.journeyLabel}>
        {positionLabel ? <small className={styles.journeyPosition}>{positionLabel}</small> : null}
        {milestone.label}
      </span>
      <span className={styles.journeyState}>{stateLabel}</span>
    </li>
  );
}

export function RunJourneyStrip({ journey }: { journey: JourneyMilestone[] }) {
  const mobileWindow = journeyWindow(journey);
  return (
    <section className={styles.journeySection} aria-labelledby="run-journey-title">
      <h2 className={styles.visuallyHidden} id="run-journey-title">Migration journey</h2>
      <ol className={`${styles.journeyList} ${styles.journeyDesktop}`} aria-label="Migration journey">
        {journey.map((milestone) => <MilestoneItem key={milestone.key} milestone={milestone} />)}
      </ol>
      <div className={styles.journeyMobile}>
        <ol className={`${styles.journeyList} ${styles.journeyMobileWindow}`} aria-label="Current migration window">
          {mobileWindow.map((item) => (
            <MilestoneItem key={item.position} milestone={item.milestone} position={item.position} />
          ))}
        </ol>
        <details className={styles.journeyMobileDisclosure}>
          <summary>Show full migration journey</summary>
          <ol className={`${styles.journeyList} ${styles.journeyMobileFullList}`} aria-label="Full migration journey">
            {journey.map((milestone) => <MilestoneItem key={milestone.key} milestone={milestone} />)}
          </ol>
        </details>
      </div>
    </section>
  );
}
