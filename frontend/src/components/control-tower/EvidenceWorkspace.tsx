"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { ArtifactContentResponse } from "@/api/migrations";
import type { ArtifactRefDto } from "@/types/generated/api";
import { presentArtifact, sortArtifactPresentations, type ArtifactCategory, type ArtifactPresentation } from "@/presentation/artifacts";
import { ArtifactPreviewPanel } from "@/components/ArtifactPreviewPanel";
import styles from "./EvidenceWorkspace.module.css";

type EvidenceFilter = "relevant" | "decisions" | "failures" | "commands" | "reports" | "all";

type EvidenceWorkspaceProps = {
  artifacts: ArtifactPresentation[] | ArtifactRefDto[];
  loadArtifact?: (artifactId: string) => Promise<ArtifactContentResponse>;
};

const FILTER_LABELS: Array<{ value: EvidenceFilter; label: string }> = [
  { value: "relevant", label: "Relevant" },
  { value: "decisions", label: "Decisions" },
  { value: "failures", label: "Failures" },
  { value: "commands", label: "Commands" },
  { value: "reports", label: "Reports" },
  { value: "all", label: "All" },
];

function asPresentations(artifacts: EvidenceWorkspaceProps["artifacts"]): ArtifactPresentation[] {
  return artifacts.map((artifact) => "title" in artifact ? artifact : presentArtifact(artifact));
}

function matchesFilter(presentation: ArtifactPresentation, filter: EvidenceFilter): boolean {
  if (filter === "all") return true;
  if (filter === "relevant") return presentation.category !== "other";
  const categoryByFilter: Record<Exclude<EvidenceFilter, "relevant" | "all">, ArtifactCategory | "diagnostic"> = {
    decisions: "gate",
    failures: "diagnostic",
    commands: "command",
    reports: "report",
  };
  return presentation.category === categoryByFilter[filter];
}

function formatArtifactDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Timestamp unavailable" : date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function EvidenceWorkspace({ artifacts, loadArtifact }: EvidenceWorkspaceProps) {
  const presentations = useMemo(() => sortArtifactPresentations(asPresentations(artifacts)), [artifacts]);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<EvidenceFilter>("all");
  const [stage, setStage] = useState("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const resultButtonRefs = useRef(new Map<string, HTMLButtonElement>());
  const detailHeadingRef = useRef<HTMLHeadingElement>(null);
  const previousSelectedId = useRef<string | null>(null);

  const stageOptions = useMemo(
    () => [...new Set(presentations.map((presentation) => presentation.stageLabel))].sort((left, right) => left.localeCompare(right)),
    [presentations],
  );
  const visible = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return presentations.filter((presentation) => {
      const searchMatch = normalized.length === 0 || presentation.searchableText.toLowerCase().includes(normalized);
      return searchMatch && matchesFilter(presentation, filter) && (stage === "all" || presentation.stageLabel === stage);
    });
  }, [filter, presentations, query, stage]);
  const selected = visible.find((presentation) => presentation.artifact.artifact_id === selectedId)
    ?? presentations.find((presentation) => presentation.artifact.artifact_id === selectedId)
    ?? null;

  useEffect(() => {
    if (selectedId) {
      detailHeadingRef.current?.focus();
    } else if (previousSelectedId.current) {
      resultButtonRefs.current.get(previousSelectedId.current)?.focus();
    }
    previousSelectedId.current = selectedId;
  }, [selectedId]);

  return (
    <section className={styles.workspace} data-detail-active={selected ? "true" : "false"} aria-labelledby="evidence-workspace-heading">
      <header className={styles.heading}>
        <div>
          <h2 id="evidence-workspace-heading">Evidence</h2>
          <p>Search the immutable artifacts that prove this migration state.</p>
        </div>
        <span className={styles.count} aria-live="polite">{visible.length} of {presentations.length} artifacts</span>
      </header>

      <div className={styles.splitView}>
        <aside className={styles.listPane} aria-label="Evidence results">
          <div className={styles.controls}>
            <label>
              <span>Search</span>
              <input
                aria-label="Search evidence"
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Title, path, checksum, or type"
              />
            </label>
            <label>
              <span>Category</span>
              <select aria-label="Evidence category" value={filter} onChange={(event) => setFilter(event.target.value as EvidenceFilter)}>
                {FILTER_LABELS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
            <label>
              <span>Stage</span>
              <select aria-label="Evidence stage" value={stage} onChange={(event) => setStage(event.target.value)}>
                <option value="all">All stages</option>
                {stageOptions.map((option) => <option key={option} value={option}>{option}</option>)}
              </select>
            </label>
          </div>

          {visible.length === 0 ? (
            <p className={styles.empty}>No evidence matches these filters.</p>
          ) : (
            <ul className={styles.results}>
              {visible.map((presentation) => (
                <li key={presentation.artifact.artifact_id}>
                  <button
                    type="button"
                    className={styles.resultButton}
                    ref={(node) => {
                      if (node) resultButtonRefs.current.set(presentation.artifact.artifact_id, node);
                      else resultButtonRefs.current.delete(presentation.artifact.artifact_id);
                    }}
                    data-selected={presentation.artifact.artifact_id === selectedId ? "true" : "false"}
                    onClick={() => setSelectedId(presentation.artifact.artifact_id)}
                  >
                    <strong>{presentation.title}</strong>
                    <span>{presentation.stageLabel} · {presentation.category} · {formatArtifactDate(presentation.artifact.created_at)}</span>
                    <code className={styles.resultPath} title={presentation.rawPath}>{presentation.rawPath}</code>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <section className={styles.detailPane} aria-label="Evidence detail">
          {selected ? (
            <>
              <button className={styles.backButton} type="button" onClick={() => setSelectedId(null)}>Back to evidence</button>
              <ArtifactPreviewPanel key={`${selected.artifact.artifact_id}|${selected.artifact.checksum}`} presentation={selected} headingRef={detailHeadingRef} loadArtifact={loadArtifact} />
            </>
          ) : (
            <div className={styles.placeholder}>
              <h3>Select evidence</h3>
              <p>Choose an artifact to inspect its preview and provenance.</p>
            </div>
          )}
        </section>
      </div>
    </section>
  );
}
