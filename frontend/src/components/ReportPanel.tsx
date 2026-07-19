import type { MigrationRunDto as MigrationRun } from "@/types/generated/api";
import styles from "./ControlTowerShell.module.css";

interface ReportPanelProps {
  run: MigrationRun;
  onOpenReport?: () => void;
  onOpenDelivery?: () => void;
  onOpenAssurance?: () => void;
}

export function ReportPanel({ run, onOpenReport, onOpenDelivery, onOpenAssurance }: ReportPanelProps) {
  const isFinalPhase = run.run_phase === "FINAL_ASSURANCE" || run.run_phase === "DELIVERY_REPORTING";
  const isCompleted = run.status === "COMPLETED";

  return (
    <section className={styles.panel} role="region" aria-label="Delivery and report panel">
      <h2>Final Assurance, Delivery &amp; Report</h2>
      <p>
        Phase: <strong>{run.run_phase}</strong> &mdash; Status: <strong>{run.status}</strong>
      </p>
      {!isFinalPhase && !isCompleted && (
        <p>This run has not yet reached the final assurance phase.</p>
      )}
      {isCompleted && (
        <p>Run is completed. Final artifacts and reports are available.</p>
      )}
      {(isFinalPhase || isCompleted) && (
        <div className={styles.inlineActions}>
          {onOpenAssurance && (
            <button
              type="button"
              className={styles.actionButton}
              onClick={onOpenAssurance}
              aria-label="Open final assurance panel"
            >
              Final Assurance (G13)
            </button>
          )}
          {onOpenDelivery && (
            <button
              type="button"
              className={styles.actionButton}
              onClick={onOpenDelivery}
              aria-label="Open delivery panel"
            >
              Delivery (G14)
            </button>
          )}
          {onOpenReport && (
            <button
              type="button"
              className={styles.actionButton}
              onClick={onOpenReport}
              aria-label="Open report panel"
            >
              Report (G15)
            </button>
          )}
        </div>
      )}
    </section>
  );
}
