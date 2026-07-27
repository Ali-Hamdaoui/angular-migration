"use client";

import { useEffect } from "react";

export type ControlTowerSection =
  | "overview"
  | "pipeline"
  | "analysis"
  | "feasibility"
  | "planning"
  | "discovery"
  | "parity"
  | "evidence"
  | "llm"
  | "events"
  | "assistant";

type NavigationGroup = { label: string; items: Array<{ key: ControlTowerSection; label: string; icon: string }> };

const groups: NavigationGroup[] = [
  { label: "Run", items: [{ key: "overview", label: "Overview", icon: "◈" }, { key: "pipeline", label: "Pipeline", icon: "↗" }] },
  { label: "Intelligence", items: [
    { key: "analysis", label: "Analysis & G04", icon: "⌁" },
    { key: "feasibility", label: "Feasibility & G05", icon: "◇" },
    { key: "planning", label: "Planning & G06", icon: "≡" },
    { key: "discovery", label: "Discovery", icon: "⌕" },
    { key: "parity", label: "Parity", icon: "◎" },
  ] },
  { label: "Evidence", items: [
    { key: "evidence", label: "Files & Artifacts", icon: "▤" },
    { key: "llm", label: "LLM Diagnostics", icon: "✦" },
    { key: "events", label: "Workflow Events", icon: "≋" },
    { key: "assistant", label: "Assistant", icon: "✧" },
  ] },
];

export function ControlTowerSidebar({ activeSection, open, onSelect, onClose }: { activeSection: ControlTowerSection; open: boolean; onSelect: (section: ControlTowerSection) => void; onClose: () => void }) {
  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose, open]);

  return <>
    <div className={`controlTowerScrim${open ? " controlTowerScrimOpen" : ""}`} onClick={onClose} aria-hidden="true" />
    <aside className={`controlTowerSidebar${open ? " controlTowerSidebarOpen" : ""}`} aria-label="Control Tower navigation">
      <div className="controlTowerSidebarBrand"><span className="controlTowerBrandMark" aria-hidden="true">AM</span><div><strong>Control Tower</strong><span>Migration operations</span></div><button className="controlTowerClose" type="button" onClick={onClose} aria-label="Close navigation">×</button></div>
      <nav aria-label="Run sections">
        {groups.map((group) => <div className="controlTowerNavGroup" key={group.label}><p>{group.label}</p>{group.items.map((item) => <button id={`${item.key}-navigation-item`} key={item.key} type="button" className={`controlTowerNavItem${activeSection === item.key ? " controlTowerNavItemActive" : ""}`} onClick={() => { onSelect(item.key); onClose(); }} aria-current={activeSection === item.key ? "page" : undefined}><span aria-hidden="true">{item.icon}</span>{item.label}</button>)}</div>)}
      </nav>
      <div className="controlTowerSidebarFoot"><span className="controlTowerLiveDot" aria-hidden="true" /> Backend-authoritative UI</div>
    </aside>
  </>;
}
