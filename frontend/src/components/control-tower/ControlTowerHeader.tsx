import type { AuthoritativeConnectionStatus } from "@/hooks/useAuthoritativeRun";
import type { AuthoritativeRunStateDto } from "@/types/generated/api";

export function ControlTowerHeader({ runId, status, connectionLabel, onMenu, state }: { runId: string; status: AuthoritativeConnectionStatus; connectionLabel: string; onMenu: () => void; state: AuthoritativeRunStateDto }) {
  return <header className="controlTowerHeader">
    <button className="controlTowerMenuButton" type="button" onClick={onMenu} aria-label="Open navigation">☰</button>
    <div className="controlTowerHeaderTitle"><span className="controlTowerEyebrow">Angular Migration Control Tower · Live run</span><strong>{state.source_path.split(/[\\/]/).at(-1)} → {state.target_output_path.split(/[\\/]/).at(-1)}</strong><span className="controlTowerRunId">{runId}</span></div>
    <div className="controlTowerHeaderMeta"><span className={`controlTowerConnection controlTowerConnection-${status}`}><i aria-hidden="true" />{connectionLabel}</span></div>
  </header>;
}
