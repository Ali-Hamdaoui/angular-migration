"use client";

import { useRouter } from "next/navigation";
import styles from "./MigrationSetupForm.module.css";

export function MigrationSetupForm() {
  const router = useRouter();
  return <main className={styles.page}><section className={styles.panel}><p className={styles.kicker}>Control Tower</p><h1>Start mock migration</h1><p>This form collects setup intent only. Sprint 0 does not create or execute a real migration.</p><form onSubmit={(event) => { event.preventDefault(); router.push("/migrations/mock-run-angular-18-to-21"); }}><label>Source path<input name="sourcePath" required placeholder="C:\\projects\\angular-18-app" /></label><label>Target output path<input name="targetOutputPath" required placeholder="C:\\migration-output" /></label><label>Target Angular family<select name="targetAngularFamily" defaultValue="21.x"><option>21.x</option></select></label><label>Migration mode<select name="migrationMode" defaultValue="strict-functional-parity"><option value="strict-functional-parity">Strict functional parity</option></select></label><label className={styles.checkbox}><input name="autoApprovalEnabled" type="checkbox" />Enable auto-approval where future backend policy allows</label><button type="submit">Start Mock Migration</button></form></section></main>;
}