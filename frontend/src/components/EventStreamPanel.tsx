import type { MigrationEventDto } from "@/types/generated/api";
import styles from "./ControlTowerShell.module.css";

export function EventStreamPanel({ events }: { events: MigrationEventDto[] }) {
  return <section className={styles.panel}><h2>Live event stream</h2>{events.length === 0 ? <p className={styles.note}>Waiting for backend events…</p> : <ol className={styles.eventList}>{events.map((event) => <li key={event.event_id} className={styles.eventItem}><code className={styles.eventType}>{event.event_type}</code><span className={styles.eventTime}>{event.occurred_at}</span>{event.stage_id && <span className={styles.eventStage}>{event.stage_id}</span>}</li>)}</ol>}</section>;
}
