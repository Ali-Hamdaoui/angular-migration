import styles from "./ControlTowerShell.module.css";

export function StatusPill({ value }: { value: string }) {
  return <span className={styles.status}>{value.replaceAll("_", " ")}</span>;
}