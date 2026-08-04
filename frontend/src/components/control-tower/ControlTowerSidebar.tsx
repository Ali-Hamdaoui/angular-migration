"use client";

import { useEffect } from "react";
import { NAV_GROUPS, PRODUCT_NAME } from "@/content/uiCopy";

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

type NavigationGroup = { label: string; items: Array<{ key: ControlTowerSection; label: string; icon: string }> };

const ICONS: Record<ControlTowerSection, string> = {
  overview: "◈",
  pipeline: "↗",
  transformation: "⇢",
  analysis: "⌁",
  feasibility: "◇",
  planning: "≡",
  discovery: "⌕",
  parity: "◎",
  evidence: "▤",
  llm: "✦",
  events: "≋",
};

const groups: NavigationGroup[] = NAV_GROUPS.map((group) => ({
  label: group.label,
  items: group.items.map((item) => ({ key: item.key as ControlTowerSection, label: item.label, icon: ICONS[item.key as ControlTowerSection] })),
}));

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
      <div className="controlTowerSidebarBrand"><span className="controlTowerBrandMark" aria-hidden="true">AM</span><div><strong>{PRODUCT_NAME}</strong><span>Guided Angular upgrades</span></div><button className="controlTowerClose" type="button" onClick={onClose} aria-label="Close navigation">×</button></div>
      <nav aria-label="Run sections">
        {groups.map((group) => <div className="controlTowerNavGroup" key={group.label}><p>{group.label}</p>{group.items.map((item) => <button id={`${item.key}-navigation-item`} key={item.key} type="button" className={`controlTowerNavItem${activeSection === item.key ? " controlTowerNavItemActive" : ""}`} onClick={() => { onSelect(item.key); onClose(); }} aria-current={activeSection === item.key ? "page" : undefined}><span aria-hidden="true">{item.icon}</span>{item.label}{item.key === "transformation" && actionRequired ? <span className="controlTowerNavAction">Action required</span> : null}</button>)}</div>)}
      </nav>
      <div className="controlTowerSidebarFoot"><span className="controlTowerLiveDot" aria-hidden="true" /> Live data from the migration backend</div>
    </aside>
  </>;
}