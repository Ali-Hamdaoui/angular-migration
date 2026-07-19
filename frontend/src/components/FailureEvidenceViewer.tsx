"use client";

import { useMemo, useState } from "react";
import type { FailureDiagnosticDto, FailureEvidenceDto } from "@/types/generated/api";
import styles from "./FailureEvidenceViewer.module.css";

/* ------------------------------------------------------------------ */
/*  Props                                                              */
/* ------------------------------------------------------------------ */
export type FailureEvidenceViewerProps = {
  /** The evidence payload, or null when not yet loaded / empty. */
  evidence: FailureEvidenceDto | null;
  /** True while evidence is being fetched. */
  loading: boolean;
  /** A user-facing error message, or null. */
  error: string | null;
};

/* ------------------------------------------------------------------ */
/*  Helper: format origin into a readable label                       */
/* ------------------------------------------------------------------ */
function originLabel(origin: string): string {
  return origin
    .replace(/^pre_existing_/, "pre-existing ")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/* ------------------------------------------------------------------ */
/*  Helper: confidence → class name                                   */
/* ------------------------------------------------------------------ */
function confidenceClass(value: number): string {
  if (value >= 0.8) return styles.confidenceHigh;
  if (value >= 0.5) return styles.confidenceMedium;
  return styles.confidenceLow;
}

/* ------------------------------------------------------------------ */
/*  Helper: origin → CSS class                                         */
/* ------------------------------------------------------------------ */
function originClass(origin: string): string {
  switch (origin) {
    case "pre_existing_unchanged":
      return styles.originPreExistingUnchanged;
    case "pre_existing_changed":
      return styles.originPreExistingChanged;
    case "migration_caused":
      return styles.originMigrationCaused;
    case "resolved_pre_existing":
      return styles.originResolvedPreExisting;
    default:
      return styles.originUnknown;
  }
}

/* ------------------------------------------------------------------ */
/*  Helper: severity → CSS class                                       */
/* ------------------------------------------------------------------ */
function severityClass(severity?: string): string {
  if (!severity) return styles.severityDefault;
  const s = severity.toLowerCase();
  if (s === "error") return styles.severityError;
  if (s === "warning" || s === "warn") return styles.severityWarning;
  if (s === "info") return styles.severityInfo;
  return styles.severityDefault;
}

/* ------------------------------------------------------------------ */
/*  Helper: truncate sha256 fingerprint                                */
/* ------------------------------------------------------------------ */
function truncateFingerprint(fp: string): string {
  const prefix = "sha256:";
  if (fp.startsWith(prefix)) {
    const hash = fp.slice(prefix.length);
    if (hash.length > 16) return `${prefix}${hash.slice(0, 16)}…`;
    return fp;
  }
  // Not sha256 — just truncate the whole thing
  return fp.length > 24 ? `${fp.slice(0, 24)}…` : fp;
}

/* ------------------------------------------------------------------ */
/*  Helper: format parser type for display                             */
/* ------------------------------------------------------------------ */
function parserLabel(pt: string): string {
  return pt.replace(/_/g, " ").toUpperCase();
}

/* ------------------------------------------------------------------ */
/*  Helper: build raw output text from evidence                        */
/* ------------------------------------------------------------------ */
function buildRawOutput(evidence: FailureEvidenceDto): string {
  const parts: string[] = [];

  // Include raw_excerpt from each diagnostic that has one
  for (const diag of evidence.diagnostics) {
    if (diag.raw_excerpt) {
      parts.push(`--- ${diag.parser_type} ${diag.file_path ?? "unknown"} ---`);
      parts.push(diag.raw_excerpt);
    }
  }

  // If no raw excerpts, fall back to a summary of diagnostics
  if (parts.length === 0) {
    for (const diag of evidence.diagnostics) {
      parts.push(`[${diag.parser_type}] ${diag.message}`);
      if (diag.file_path) parts.push(`  File: ${diag.file_path}${diag.line_number != null ? `:${diag.line_number}` : ""}`);
      if (diag.code) parts.push(`  Code: ${diag.code}`);
    }
  }

  return parts.length > 0 ? parts.join("\n") : "(no raw output available)";
}

/* ------------------------------------------------------------------ */
/*  Tab IDs (constant for a11y)                                        */
/* ------------------------------------------------------------------ */
const TAB_RAW = "evidence-tab-raw";
const TAB_NORMALIZED = "evidence-tab-normalized";
const TAB_PANEL_RAW = "evidence-panel-raw";
const TAB_PANEL_NORMALIZED = "evidence-panel-normalized";

/* ================================================================== */
/*  Component                                                          */
/* ================================================================== */
export function FailureEvidenceViewer({
  evidence,
  loading,
  error,
}: FailureEvidenceViewerProps) {
  /* Tab state */
  const [activeTab, setActiveTab] = useState<"raw" | "normalized">("normalized");

  /* Filter state */
  const [filterText, setFilterText] = useState("");
  const [filterParser, setFilterParser] = useState("");

  /* --------------- Derive parser types from evidence --------------- */
  const availableParserTypes = useMemo<string[]>(() => {
    if (!evidence) return [];
    const types = new Set(evidence.diagnostics.map((d) => d.parser_type));
    return Array.from(types).sort();
  }, [evidence]);

  /* --------------- Filtered diagnostics ---------------------------- */
  const filteredDiagnostics = useMemo<FailureDiagnosticDto[]>(() => {
    if (!evidence) return [];
    let list = evidence.diagnostics;

    if (filterText) {
      const lower = filterText.toLowerCase();
      list = list.filter(
        (d) =>
          (d.file_path?.toLowerCase() ?? "").includes(lower) ||
          d.parser_type.toLowerCase().includes(lower) ||
          d.message.toLowerCase().includes(lower),
      );
    }

    if (filterParser) {
      list = list.filter((d) => d.parser_type === filterParser);
    }

    return list;
  }, [evidence, filterText, filterParser]);

  /* --------------- Keyboard navigation for tabs -------------------- */
  function onTabKeyDown(e: React.KeyboardEvent) {
    let next: "raw" | "normalized" | null = null;
    if (e.key === "ArrowRight") {
      next = activeTab === "raw" ? "normalized" : "raw";
    } else if (e.key === "ArrowLeft") {
      next = activeTab === "normalized" ? "raw" : "normalized";
    }
    if (next) {
      e.preventDefault();
      setActiveTab(next);
    }
  }

  /* ================================================================ */
  /*  RENDER: Loading                                                  */
  /* ================================================================ */
  if (loading) {
    return (
      <section className={styles.viewer} aria-labelledby="evidence-title">
        <div className={styles.loadingState} role="status" aria-live="polite">
          <span className={styles.spinner} aria-hidden="true" />
          <span>Loading failure evidence…</span>
        </div>
      </section>
    );
  }

  /* ================================================================ */
  /*  RENDER: Error                                                    */
  /* ================================================================ */
  if (error) {
    return (
      <section className={styles.viewer} aria-labelledby="evidence-title">
        <div className={styles.errorState} role="alert">
          {error}
        </div>
      </section>
    );
  }

  /* ================================================================ */
  /*  RENDER: Empty / no evidence                                      */
  /* ================================================================ */
  if (!evidence) {
    return (
      <section className={styles.viewer} aria-labelledby="evidence-title">
        <div className={styles.emptyState}>
          <p>No failure evidence available for this execution.</p>
          <p className={styles.note}>
            Evidence is generated when a command exits with a non-zero code or
            when the diagnostic pipeline captures output.
          </p>
        </div>
      </section>
    );
  }

  /* ================================================================ */
  /*  RENDER: Evidence present                                         */
  /* ================================================================ */
  const rawOutput = buildRawOutput(evidence);
  const unknownOrigin = evidence.origin === "unknown_origin" || evidence.origin === "";

  return (
    <section className={styles.viewer} aria-labelledby="evidence-title">
      {/* Title + kicker */}
      <p className={styles.kicker}>S4-F01-I03</p>
      <h2 id="evidence-title">Failure Evidence</h2>

      {/* --- Metadata bar: origin badge, fingerprint, status --- */}
      <div className={styles.statusBar}>
        {/* Origin badge */}
        <span
          className={`${styles.originBadge} ${originClass(evidence.origin)}`}
          aria-label={`Origin: ${originLabel(evidence.origin)}`}
        >
          {originLabel(evidence.origin)}
        </span>

        {/* Unknown origin alert */}
        {unknownOrigin && (
          <span className={styles.unknownState} role="status">
            Origin not determined — the failure source could not be classified.
          </span>
        )}

        {/* Fingerprint */}
        {evidence.failure_fingerprint ? (
          <span className={styles.fingerprint} aria-label="Failure fingerprint">
            {truncateFingerprint(evidence.failure_fingerprint)}
          </span>
        ) : (
          <span className={styles.unknownState} role="status">
            No fingerprint recorded.
          </span>
        )}

        {/* Status pill */}
        <span
          className={`${styles.statusPill} ${
            evidence.status === "finalized"
              ? styles.statusFinalized
              : evidence.status === "invalid"
                ? styles.statusInvalid
                : styles.statusStale
          }`}
          aria-label={`Status: ${evidence.status}`}
        >
          {evidence.status}
        </span>
      </div>

      {/* --- Stale / blocked info --- */}
      {evidence.status === "stale" && (
        <div className={styles.blockedInfo} role="status">
          This evidence record is stale. The workspace or command output has
          changed since it was captured.
        </div>
      )}

      {/* --- Metadata grid --- */}
      <div className={styles.metadataGrid} aria-label="Evidence metadata">
        <div>
          <dt>Failure ID</dt>
          <dd>{evidence.failure_id}</dd>
        </div>
        <div>
          <dt>Run ID</dt>
          <dd>{evidence.run_id}</dd>
        </div>
        <div>
          <dt>Stage</dt>
          <dd>{evidence.stage_id}</dd>
        </div>
        <div>
          <dt>Execution</dt>
          <dd>{evidence.execution_id}</dd>
        </div>
        <div>
          <dt>Workspace Fingerprint</dt>
          <dd>{truncateFingerprint(evidence.workspace_fingerprint)}</dd>
        </div>
        <div>
          <dt>Diagnostics</dt>
          <dd>{evidence.diagnostics.length}</dd>
        </div>
        <div>
          <dt>State Version</dt>
          <dd>{evidence.state_version}</dd>
        </div>
        {evidence.created_at && (
          <div>
            <dt>Captured</dt>
            <dd>{new Date(evidence.created_at).toLocaleString()}</dd>
          </div>
        )}
      </div>

      {/* --- Tab navigation --- */}
      <div
        role="tablist"
        aria-label="Evidence view mode"
        className={styles.tabList}
        onKeyDown={onTabKeyDown}
      >
        <button
          id={TAB_RAW}
          role="tab"
          aria-selected={activeTab === "raw"}
          aria-controls={TAB_PANEL_RAW}
          tabIndex={activeTab === "raw" ? 0 : -1}
          className={styles.tab}
          onClick={() => setActiveTab("raw")}
        >
          Raw Output
        </button>
        <button
          id={TAB_NORMALIZED}
          role="tab"
          aria-selected={activeTab === "normalized"}
          aria-controls={TAB_PANEL_NORMALIZED}
          tabIndex={activeTab === "normalized" ? 0 : -1}
          className={styles.tab}
          onClick={() => setActiveTab("normalized")}
        >
          Parsed Diagnostics
        </button>
      </div>

      {/* ================ TAB: Raw Output ================ */}
      <div
        id={TAB_PANEL_RAW}
        role="tabpanel"
        aria-labelledby={TAB_RAW}
        hidden={activeTab !== "raw"}
        className={styles.tabPanel}
        tabIndex={0}
      >
        <pre className={styles.rawOutput}>{rawOutput}</pre>
      </div>

      {/* ================ TAB: Parsed Diagnostics ================ */}
      <div
        id={TAB_PANEL_NORMALIZED}
        role="tabpanel"
        aria-labelledby={TAB_NORMALIZED}
        hidden={activeTab !== "normalized"}
        className={styles.tabPanel}
        tabIndex={0}
      >
        {/* Filter bar */}
        <div className={styles.filterBar}>
          <input
            type="search"
            className={styles.filterInput}
            placeholder="Filter by file path, parser type, or message…"
            aria-label="Filter diagnostics"
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
          />
          {availableParserTypes.length > 0 && (
            <select
              className={styles.filterSelect}
              aria-label="Filter by parser type"
              value={filterParser}
              onChange={(e) => setFilterParser(e.target.value)}
            >
              <option value="">All parsers</option>
              {availableParserTypes.map((pt) => (
                <option key={pt} value={pt}>
                  {parserLabel(pt)}
                </option>
              ))}
            </select>
          )}
          <span className={styles.filterCount} aria-live="polite">
            {filteredDiagnostics.length} of {evidence.diagnostics.length}{" "}
            diagnostic{evidence.diagnostics.length !== 1 ? "s" : ""}
          </span>
        </div>

        {/* Diagnostics list */}
        {filteredDiagnostics.length === 0 ? (
          <div className={styles.emptyState}>
            <p>No diagnostics match the current filters.</p>
          </div>
        ) : (
          <ul className={styles.diagnosticsList} aria-label="Parsed diagnostics">
            {filteredDiagnostics.map((diag, idx) => (
              <li key={idx} className={styles.diagnosticCard}>
                <div className={styles.diagnosticHeader}>
                  {/* Parser type badge */}
                  <span className={styles.parserBadge}>
                    {parserLabel(diag.parser_type)}
                  </span>

                  {/* Severity badge */}
                  {diag.severity && (
                    <span
                      className={`${styles.severityBadge} ${severityClass(
                        diag.severity,
                      )}`}
                    >
                      {diag.severity}
                    </span>
                  )}

                  {/* Confidence indicator */}
                  {diag.parser_confidence != null && (
                    <span
                      className={styles.confidenceBar}
                      aria-label={`Parser confidence: ${Math.round(
                        diag.parser_confidence * 100,
                      )}%`}
                    >
                      <span className={styles.confidenceTrack}>
                        <span
                          className={`${styles.confidenceFill} ${confidenceClass(
                            diag.parser_confidence,
                          )}`}
                          style={{
                            width: `${Math.round(
                              diag.parser_confidence * 100,
                            )}%`,
                          }}
                        />
                      </span>
                      <span className={styles.confidenceLabel}>
                        {Math.round(diag.parser_confidence * 100)}%
                      </span>
                    </span>
                  )}
                </div>

                {/* Error code + message */}
                <p className={styles.diagnosticMessage}>
                  {diag.code && (
                    <code
                      style={{
                        color: "#ffe8a8",
                        marginRight: "0.4rem",
                      }}
                    >
                      {diag.code}
                    </code>
                  )}
                  {diag.message}
                </p>

                {/* File location info */}
                <div className={styles.diagnosticMeta}>
                  {diag.file_path && (
                    <span>
                      File:{" "}
                      <code>
                        {diag.file_path}
                        {diag.line_number != null ? `:${diag.line_number}` : ""}
                        {diag.column != null ? `:${diag.column}` : ""}
                      </code>
                    </span>
                  )}
                  {diag.source_line && (
                    <span>
                      Source: <code>{diag.source_line}</code>
                    </span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
