import styles from "./ControlTowerShell.module.css";
import { formatStatusLabel } from "@/lib/presentationLabels";

export function StatusPill({ value }: { value: string }) {
  return <span className={styles.status}>{formatStatusLabel(value)}</span>;
}
