"use client";

import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import type { JourneyMilestone } from "@/presentation/runJourney";
import styles from "./ControlTowerLayout.module.css";

export type PipelineTab = "summary" | "command" | "evidence" | "review";

export interface PipelineStageContent {
  milestone: JourneyMilestone;
  group: "prepare" | "baseline" | "understand" | "decide" | "transform" | "validate";
  occurredAt: string | null;
  evidenceCount: number | null;
  tabs: Array<{ id: PipelineTab; label: string; panel: ReactNode }>;
}

const EMPTY_SUMMARY = <p>Not started yet — no work has reached this stage</p>;

export function PipelineStageDetail({ content }: { content: PipelineStageContent }) {
  const tabs = useMemo(() => {
    const suppliedSummary = content.tabs.find((tab) => tab.id === "summary");
    return suppliedSummary
      ? content.tabs.map((tab) => tab.id === "summary" && tab.panel == null ? { ...tab, panel: EMPTY_SUMMARY } : tab)
      : [{ id: "summary" as const, label: "Summary", panel: EMPTY_SUMMARY }, ...content.tabs];
  }, [content.tabs]);
  const [selectedTab, setSelectedTab] = useState<PipelineTab>(tabs[0].id);
  const tabRefs = useRef(new Map<PipelineTab, HTMLButtonElement>());

  useEffect(() => {
    if (!tabs.some((tab) => tab.id === selectedTab)) setSelectedTab(tabs[0].id);
  }, [selectedTab, tabs]);

  function selectAt(index: number) {
    const tab = tabs[(index + tabs.length) % tabs.length];
    setSelectedTab(tab.id);
    tabRefs.current.get(tab.id)?.focus();
  }

  function onTabKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    if (event.key === "ArrowRight") selectAt(index + 1);
    else if (event.key === "ArrowLeft") selectAt(index - 1);
    else if (event.key === "Home") selectAt(0);
    else if (event.key === "End") selectAt(tabs.length - 1);
    else return;
    event.preventDefault();
  }

  const selected = tabs.find((tab) => tab.id === selectedTab) ?? tabs[0];
  const idPrefix = `pipeline-${content.milestone.key}`;

  return (
    <>
      <div className={styles.stageTabs} role="tablist" aria-label={`${content.milestone.label} details`}>
        {tabs.map((tab, index) => {
          const selectedNow = tab.id === selected.id;
          return (
            <button
              type="button"
              role="tab"
              id={`${idPrefix}-tab-${tab.id}`}
              aria-selected={selectedNow}
              aria-controls={`${idPrefix}-panel-${tab.id}`}
              tabIndex={selectedNow ? 0 : -1}
              key={tab.id}
              ref={(node) => {
                if (node) tabRefs.current.set(tab.id, node);
                else tabRefs.current.delete(tab.id);
              }}
              onClick={() => setSelectedTab(tab.id)}
              onKeyDown={(event) => onTabKeyDown(event, index)}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
      <div
        className={styles.stagePanel}
        role="tabpanel"
        id={`${idPrefix}-panel-${selected.id}`}
        aria-labelledby={`${idPrefix}-tab-${selected.id}`}
        tabIndex={0}
      >
        {selected.panel}
      </div>
    </>
  );
}
