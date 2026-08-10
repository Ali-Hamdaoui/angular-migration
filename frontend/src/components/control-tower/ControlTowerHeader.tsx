import { ArrowRight, Circle, Menu } from "lucide-react";
import type { AuthoritativeConnectionStatus } from "@/hooks/useAuthoritativeRun";
import type { AuthoritativeRunStateDto } from "@/types/generated/api";

export function ControlTowerHeader({ runId, status, connectionLabel, onMenu, state }: { runId: string; status: AuthoritativeConnectionStatus; connectionLabel: string; onMenu: () => void; state: AuthoritativeRunStateDto }) {
  void runId;
  const sourceName = state.source_path.split(/[\\/]/).at(-1) ?? "Source";
  const targetName = state.target_output_path.split(/[\\/]/).at(-1) ?? "Target";
  return <header className="controlTowerHeader">
    <button className="controlTowerMenuButton" type="button" onClick={onMenu} aria-label="Open navigation"><Menu aria-hidden="true" size={20} /></button>
    <div className="controlTowerHeaderTitle">
      <h1 aria-label={`${sourceName} to ${targetName}`}><span>{sourceName}</span><span className="controlTowerHeadingArrow" aria-hidden="true"><ArrowRight size={20} /></span><span className="controlTowerVisuallyHidden">to</span><span>{targetName}</span></h1>
      <span>Live migration workspace</span>
    </div>
    <div className="controlTowerHeaderMeta"><span className={`controlTowerConnection controlTowerConnection-${status}`}><Circle className="controlTowerConnectionIcon" aria-hidden="true" fill="currentColor" size={8} />{connectionLabel}</span></div>
  </header>;
}
