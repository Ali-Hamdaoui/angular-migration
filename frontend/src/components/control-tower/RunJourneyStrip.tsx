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

const STATE_LABELS: Record<JourneyState, string> = {
  complete: "Complete",
  current: "Current",
  "action-required": "Action required",
  blocked: "Blocked",
  "not-reached": "Not reached",
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

export function RunJourneyStrip({ journey }: { journey: JourneyMilestone[] }) {
  return (
    <section className={styles.journeySection} aria-labelledby="run-journey-title">
      <h2 className={styles.visuallyHidden} id="run-journey-title">Migration journey</h2>
      <ol className={styles.journeyList} aria-label="Migration journey">
        {journey.map((milestone) => {
          const Icon = STATE_ICONS[milestone.state];
          const stateLabel = STATE_LABELS[milestone.state];
          return (
            <li
              aria-label={`${milestone.label}: ${stateLabel}`}
              className={styles.journeyMilestone}
              data-state={milestone.state}
              key={milestone.key}
            >
              <span className={styles.journeyMarker}>
                <Icon aria-hidden="true" size={22} strokeWidth={2} />
              </span>
              <span className={styles.journeyLabel}>{milestone.label}</span>
              <span className={styles.journeyState}>{stateLabel}</span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
