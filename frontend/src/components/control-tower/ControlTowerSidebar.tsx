"use client";

import { Activity, Circle, ClipboardList, FileText, House, ListTree, RefreshCw, Scale, ScanSearch, Search, ShieldCheck, Workflow, X, type LucideIcon } from "lucide-react";
import { useEffect } from "react";

export type ControlTowerSection =
  | "overview"
  | "pipeline"
  | "transformation"
  | "analysis"
  | "feasibility"
  | "planning"
  | "discovery"
  | "parity"
  | "evidence"
  | "llm"
  | "events";

type NavigationGroup = { label: string; items: Array<{ key: ControlTowerSection; label: string; icon: LucideIcon }> };

const groups: NavigationGroup[] = [
  { label: "Run", items: [{ key: "overview", label: "Overview", icon: House }, { key: "pipeline", label: "Pipeline", icon: Workflow }, { key: "transformation", label: "Transformation", icon: RefreshCw }] },
  { label: "Intelligence", items: [
    { key: "analysis", label: "Analysis & G04", icon: ScanSearch },
    { key: "feasibility", label: "Feasibility & G05", icon: ShieldCheck },
    { key: "planning", label: "Planning & G06", icon: ClipboardList },
    { key: "discovery", label: "Discovery", icon: Search },
    { key: "parity", label: "Parity", icon: Scale },
  ] },
  { label: "Evidence", items: [
    { key: "evidence", label: "Files & Artifacts", icon: FileText },
    { key: "llm", label: "LLM Diagnostics", icon: Activity },
    { key: "events", label: "Workflow Events", icon: ListTree },
  ] },
];

export function ControlTowerSidebar({ activeSection, open, actionRequired = false, onSelect, onClose }: { activeSection: ControlTowerSection; open: boolean; actionRequired?: boolean; onSelect: (section: ControlTowerSection) => void; onClose: () => void }) {
  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose, open]);

  return <>
    <div className={`controlTowerScrim${open ? " controlTowerScrimOpen" : ""}`} onClick={onClose} aria-hidden="true" />
    <aside className={`controlTowerSidebar${open ? " controlTowerSidebarOpen" : ""}`} aria-label="Control Tower navigation">
      <div className="controlTowerSidebarBrand"><span className="controlTowerBrandMark" aria-hidden="true">AM</span><div><strong>Control Tower</strong><span>Migration operations</span></div><button className="controlTowerClose" type="button" onClick={onClose} aria-label="Close navigation"><X aria-hidden="true" size={20} /></button></div>
      <nav aria-label="Run sections">
        {groups.map((group) => <div className="controlTowerNavGroup" key={group.label}><p>{group.label}</p>{group.items.map((item) => { const Icon = item.icon; return <button id={`${item.key}-navigation-item`} key={item.key} type="button" className={`controlTowerNavItem${activeSection === item.key ? " controlTowerNavItemActive" : ""}`} onClick={() => { onSelect(item.key); onClose(); }} aria-current={activeSection === item.key ? "page" : undefined}><Icon aria-hidden="true" size={18} />{item.label}{item.key === "transformation" && actionRequired ? <span className="controlTowerNavAction">Action required</span> : null}</button>; })}</div>)}
      </nav>
      <div className="controlTowerSidebarFoot"><Circle className="controlTowerLiveDot" aria-hidden="true" fill="currentColor" size={8} /> Backend-authoritative UI</div>
    </aside>
  </>;
}
