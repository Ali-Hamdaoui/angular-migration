import { ArrowRight, Circle, Menu } from "lucide-react";
import type { AuthoritativeConnectionStatus } from "@/hooks/useAuthoritativeRun";
import type { AuthoritativeRunStateDto } from "@/types/generated/api";

export function ControlTowerHeader({ runId, status, connectionLabel, onMenu, state }: { runId: string; status: AuthoritativeConnectionStatus; connectionLabel: string; onMenu: () => void; state: AuthoritativeRunStateDto }) {
  return <header className="controlTowerHeader">
    <button className="controlTowerMenuButton" type="button" onClick={onMenu} aria-label="Open navigation"><Menu aria-hidden="true" size={20} /></button>
    <div className="controlTowerHeaderTitle"><span className="controlTowerEyebrow">Angular Migration Factory / Live run</span><strong><span>{state.source_path.split(/[\\/]/).at(-1)}</span><ArrowRight aria-hidden="true" size={16} /><span>{state.target_output_path.split(/[\\/]/).at(-1)}</span></strong><span className="controlTowerRunId">{runId}</span></div>
    <div className="controlTowerHeaderMeta"><span className={`controlTowerConnection controlTowerConnection-${status}`}><Circle className="controlTowerConnectionIcon" aria-hidden="true" fill="currentColor" size={8} />{connectionLabel}</span></div>
  </header>;
}
