import styles from "./ControlTowerShell.module.css";

export function AssistantPanel() {
  return <section className={styles.panel}><h2>Assistant</h2><p>The assistant entry point will explain backend state and submit structured requests. It cannot execute migrations or approve gates directly.</p><button type="button" disabled>Assistant unavailable in Sprint 0 shell</button></section>;
}