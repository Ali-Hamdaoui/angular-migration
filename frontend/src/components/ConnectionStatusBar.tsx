import type { ConnectionStatus } from "@/hooks/useMigrationEvents";
import styles from "./ControlTowerShell.module.css";

const STATUS_LABELS: Record<ConnectionStatus, string> = {
  connecting: "Connecting to backend event stream…",
  open: "Live — receiving backend events",
  reconnecting: "Connection lost. Reconnecting…",
  closed: "Event stream closed.",
};

export function ConnectionStatusBar({ status }: { status: ConnectionStatus }) {
  if (status === "open") return null;
  return <div className={styles.connectionBar} role="status" aria-live="polite">{STATUS_LABELS[status]}</div>;
}
