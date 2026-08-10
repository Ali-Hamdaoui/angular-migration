"use client";

import { Activity, Circle, FolderSearch, GitBranch, LayoutDashboard, X, type LucideIcon } from "lucide-react";
import { useEffect, type ReactNode } from "react";

export type ControlTowerSection = "overview" | "pipeline" | "evidence" | "diagnostics";

const NAVIGATION: Array<{ key: ControlTowerSection; label: string; icon: LucideIcon }> = [
  { key: "overview", label: "Overview", icon: LayoutDashboard },
  { key: "pipeline", label: "Pipeline", icon: GitBranch },
  { key: "evidence", label: "Evidence", icon: FolderSearch },
  { key: "diagnostics", label: "Diagnostics", icon: Activity },
];

export function ControlTowerSidebar({
  activeSection,
  open,
  actionRequired = false,
  assistant,
  onSelect,
  onClose,
}: {
  activeSection: ControlTowerSection;
  open: boolean;
  actionRequired?: boolean;
  assistant?: ReactNode;
  onSelect: (section: ControlTowerSection) => void;
  onClose: () => void;
}) {
  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose, open]);

  return <>
    <div className={`controlTowerScrim${open ? " controlTowerScrimOpen" : ""}`} onClick={onClose} aria-hidden="true" />
    <aside className={`controlTowerSidebar${open ? " controlTowerSidebarOpen" : ""}`} aria-label="Control Tower navigation">
      <div className="controlTowerSidebarBrand">
        <span className="controlTowerBrandMark" aria-hidden="true">AM</span>
        <div><strong>Angular Migration Factory</strong><span>Journey Command Center</span></div>
        <button className="controlTowerClose" type="button" onClick={onClose} aria-label="Close navigation"><X aria-hidden="true" size={20} /></button>
      </div>
      <nav className="controlTowerNav" aria-label="Run sections">
        {NAVIGATION.map((item) => {
          const Icon = item.icon;
          const itemActionRequired = item.key === "pipeline" && actionRequired;
          return (
            <button
              id={`${item.key}-navigation-item`}
              key={item.key}
              type="button"
              className={`controlTowerNavItem${activeSection === item.key ? " controlTowerNavItemActive" : ""}`}
              data-action-required={itemActionRequired ? "true" : undefined}
              onClick={() => { onSelect(item.key); onClose(); }}
              aria-current={activeSection === item.key ? "page" : undefined}
            >
              <Icon aria-hidden="true" size={20} />
              <span>{item.label}</span>
              {itemActionRequired ? <> <span className="controlTowerNavAction">Action required</span></> : null}
            </button>
          );
        })}
      </nav>
      {assistant ? <div className="controlTowerAssistantSlot">{assistant}</div> : null}
      <div className="controlTowerSidebarFoot"><Circle className="controlTowerLiveDot" aria-hidden="true" fill="currentColor" size={8} /> Backend-authoritative UI</div>
    </aside>
  </>;
}
