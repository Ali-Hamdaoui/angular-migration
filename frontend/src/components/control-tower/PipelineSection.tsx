"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronDown, ChevronRight } from "lucide-react";
import type { JourneyKey, JourneyMilestone, JourneyState } from "@/presentation/runJourney";
import { PipelineStageDetail, type PipelineStageContent } from "./PipelineStageDetail";
import styles from "./ControlTowerLayout.module.css";

type PipelineGroup = PipelineStageContent["group"];

const GROUPS: Array<{ id: PipelineGroup; label: string }> = [
  { id: "prepare", label: "Prepare" },
  { id: "baseline", label: "Baseline" },
  { id: "understand", label: "Understand" },
  { id: "decide", label: "Decide" },
  { id: "transform", label: "Transform" },
  { id: "validate", label: "Validate" },
];

const DEFAULT_GROUP_BY_KEY: Record<JourneyKey, PipelineGroup> = {
  setup: "prepare",
  readiness: "prepare",
  g01: "prepare",
  baseline: "baseline",
  discovery: "understand",
  feasibility: "decide",
  plan: "decide",
  "18-to-19": "transform",
  "19-to-20": "transform",
  "20-to-21": "transform",
  validate: "validate",
  complete: "validate",
};

const STATE_LABELS: Record<JourneyState, string> = {
  complete: "Completed",
  current: "Running",
  "action-required": "Waiting for approval",
  blocked: "Blocked",
  "not-reached": "Not started",
  unavailable: "Not available",
};

const STAGE_CLASS_BY_STATE: Record<JourneyState, string> = {
  complete: styles.stageComplete,
  current: styles.stageCurrent,
  "action-required": styles.stageActionRequired,
  blocked: styles.stageBlocked,
  "not-reached": styles.stageNotReached,
  unavailable: styles.stageUnavailable,
};

const SUMMARY_TONE_BY_STATE: Record<JourneyState, "success" | "accent" | "warning" | "neutral"> = {
  complete: "success",
  current: "accent",
  "action-required": "warning",
  blocked: "warning",
  "not-reached": "neutral",
  unavailable: "neutral",
};

function automaticKey(journey: JourneyMilestone[]): JourneyKey | undefined {
  return journey.find((milestone) => milestone.state === "action-required")?.key
    ?? journey.find((milestone) => milestone.state === "current")?.key;
}

function stageClass(state: JourneyState): string {
  return `${styles.stageRow} ${STAGE_CLASS_BY_STATE[state]}`;
}

function formatOccurredAt(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function defaultExpandedKey(journey: JourneyMilestone[]): JourneyKey | undefined {
  return journey.find((milestone) => milestone.state === "not-reached" || milestone.state === "unavailable")?.key
    ?? [...journey].reverse().find((milestone) => milestone.state === "complete")?.key
    ?? journey[0]?.key;
}

export function PipelineSection({
  journey,
  stageContent,
  focusStage,
  expandedKey: controlledExpandedKey,
  onExpandedKeyChange,
}: {
  journey: JourneyMilestone[];
  stageContent: PipelineStageContent[];
  focusStage?: JourneyKey;
  expandedKey?: JourneyKey;
  onExpandedKeyChange?: (key: JourneyKey) => void;
}) {
  const contentByKey = useMemo(
    () => new Map(stageContent.map((content) => [content.milestone.key, content])),
    [stageContent],
  );
  const stages = useMemo(
    () => journey.map((milestone): PipelineStageContent => {
      const content = contentByKey.get(milestone.key);
      return content
        ? { ...content, milestone }
        : {
            milestone,
            group: DEFAULT_GROUP_BY_KEY[milestone.key],
            occurredAt: null,
            evidenceCount: null,
            tabs: [],
          };
    }),
    [contentByKey, journey],
  );
  const authoritativeKey = automaticKey(journey);
  const initialKey = focusStage ?? authoritativeKey ?? defaultExpandedKey(journey);
  const [internalExpandedKey, setInternalExpandedKey] = useState<JourneyKey | undefined>(initialKey);
  const expandedKey = controlledExpandedKey ?? internalExpandedKey;
  const setExpandedKey = useCallback((key: JourneyKey | undefined) => {
    setInternalExpandedKey(key);
    if (key) onExpandedKeyChange?.(key);
  }, [onExpandedKeyChange]);
  const previousAuthoritativeKey = useRef(authoritativeKey);
  const previousFocusStage = useRef(focusStage);

  useEffect(() => {
    if (focusStage && focusStage !== previousFocusStage.current && contentByKey.has(focusStage)) {
      setExpandedKey(focusStage);
    }
    previousFocusStage.current = focusStage;
  }, [contentByKey, focusStage, setExpandedKey]);

  useEffect(() => {
    if (authoritativeKey && authoritativeKey !== previousAuthoritativeKey.current) {
      setExpandedKey(authoritativeKey);
    }
    previousAuthoritativeKey.current = authoritativeKey;
  }, [authoritativeKey, setExpandedKey]);

  useEffect(() => {
    if (expandedKey && journey.some((milestone) => milestone.key === expandedKey)) return;
    setExpandedKey(authoritativeKey ?? defaultExpandedKey(journey));
  }, [authoritativeKey, expandedKey, journey, setExpandedKey]);

  const expanded = stages.find((stage) => stage.milestone.key === expandedKey);
  const completeCount = journey.filter((milestone) => milestone.state === "complete").length;

  return (
    <section className={styles.pipelineSection} aria-label="Migration workflow progress">
      <div className={styles.pipelineSummary}>
        <div>
          <span className={styles.kicker}>Authoritative progression</span>
          <h3>{expanded?.milestone.label ?? "No active stage"}</h3>
          <p>{completeCount} of {journey.length} milestones confirmed complete</p>
        </div>
        <strong data-tone={expanded ? SUMMARY_TONE_BY_STATE[expanded.milestone.state] : "neutral"}>{expanded ? STATE_LABELS[expanded.milestone.state] : "Not available"}</strong>
      </div>

      <div className={styles.pipelineGroups}>
        {GROUPS.map((group) => {
          const groupStages = stages.filter((stage) => stage.group === group.id);
          return (
            <section className={styles.pipelineGroup} key={group.id} aria-labelledby={`pipeline-group-${group.id}`}>
              <h3 id={`pipeline-group-${group.id}`}>{group.label}</h3>
              <ol className={styles.stageList}>
                {groupStages.map((stage) => {
                  const { milestone } = stage;
                  const isOpen = milestone.key === expandedKey;
                  const statusLabel = STATE_LABELS[milestone.state];
                  const milestoneIndex = stages.findIndex((item) => item.milestone.key === milestone.key);
                  return (
                    <li className={stageClass(milestone.state)} key={milestone.key}>
                      <button
                        type="button"
                        className={styles.stageButton}
                        onClick={() => setExpandedKey(milestone.key)}
                        aria-expanded={isOpen}
                        aria-controls={`pipeline-stage-${milestone.key}`}
                        aria-label={`${milestone.label}: ${statusLabel}`}
                      >
                        <span className={styles.stageMarker} aria-hidden="true">
                          {milestone.state === "complete" ? <Check size={18} /> : String(milestoneIndex + 1).padStart(2, "0")}
                        </span>
                        <span>
                          <strong>{milestone.label}</strong>
                          <small>
                            {statusLabel}
                            {stage.occurredAt ? ` · ${formatOccurredAt(stage.occurredAt)}` : ""}
                            {stage.evidenceCount != null ? ` · ${stage.evidenceCount} evidence item${stage.evidenceCount === 1 ? "" : "s"}` : ""}
                          </small>
                        </span>
                        {isOpen ? <ChevronDown size={18} aria-hidden="true" /> : <ChevronRight size={18} aria-hidden="true" />}
                      </button>
                      {isOpen ? (
                        <div className={styles.stageDetails} id={`pipeline-stage-${milestone.key}`}>
                          <PipelineStageDetail content={stage} />
                        </div>
                      ) : null}
                    </li>
                  );
                })}
              </ol>
            </section>
          );
        })}
      </div>
    </section>
  );
}
