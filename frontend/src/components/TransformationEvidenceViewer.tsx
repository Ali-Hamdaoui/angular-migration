"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { generateTransformationEvidence, getTransformationEvidence } from "@/api/transformations";
import { getArtifactById } from "@/api/migrations";
import { ApiClientError } from "@/api/client";
import type { TransformationEvidenceResponse, TransformationArtifactRef, TransformationIntegrityStatus } from "@/types/transformation";
import type { AuthoritativeConnectionStatus } from "@/hooks/useAuthoritativeRun";
import type { WorkflowEventDto } from "@/types/generated/api";
import { StatusPill } from "@/components/StatusPill";
import { TransformationFileTree } from "@/components/TransformationFileTree";
import { UnifiedDiffViewer } from "@/components/UnifiedDiffViewer";

interface ChangedFileEntry {
  file_path: string;
  change_type: string;
  classification: string;
  lines_added: number;
  lines_removed: number;
  is_generated?: boolean;
  is_binary?: boolean;
}

interface PackageChangeSummary {
  dependencies_added: string[];
  dependencies_removed: string[];
  dependencies_updated: Array<{ name: string; from: string; to: string }>;
  dev_dependencies_added: string[];
  dev_dependencies_removed: string[];
  dev_dependencies_updated: Array<{ name: string; from: string; to: string }>;
  angular_version_before?: string;
  angular_version_after?: string;
  other_major_changes: string[];
}

interface ForbiddenChangeEntry {
  file_path: string;
  reason: string;
  risk_level: string;
  suggestion?: string;
}

type ViewState = "loading" | "empty" | "running" | "success" | "blocked" | "stale" | "failure" | "reconnecting" | "missing-artifact";

interface Props {
  runId: string;
  stageId: string;
  expectedStateVersion: number;
  connectionStatus?: AuthoritativeConnectionStatus;
  workflowEvents?: WorkflowEventDto[];
  onAuthoritativeRefresh?: () => Promise<void> | void;
}

const MAX_VISIBLE_FILES = 50;

const STATUS_PILL_MAP: Record<ViewState, string> = {
  loading: "LOADING",
  empty: "PENDING",
  running: "RUNNING",
  success: "PASSED",
  blocked: "BLOCKED",
  stale: "STALE",
  failure: "FAILED",
  reconnecting: "RECONNECTING",
  "missing-artifact": "MISSING",
};

function viewStateFromIntegrity(integrity: TransformationIntegrityStatus, complete: boolean): ViewState {
  switch (integrity) {
    case "valid": return complete ? "success" : "blocked";
    case "stale": return "stale";
    case "tampered": return "failure";
    case "missing": return "missing-artifact";
    case "in_progress": return "running";
    case "blocked": return "blocked";
    case "failed": return "failure";
  }
}

const INTEGRITY_LABELS: Record<TransformationIntegrityStatus, { label: string; color: string }> = {
  valid: { label: "Valid", color: "text-green-600" },
  stale: { label: "Stale", color: "text-amber-600" },
  tampered: { label: "Tampered", color: "text-red-600" },
  missing: { label: "Missing", color: "text-gray-400" },
  in_progress: { label: "In Progress", color: "text-blue-600" },
  blocked: { label: "Blocked", color: "text-amber-600" },
  failed: { label: "Failed", color: "text-red-600" },
};

async function sha256Hex(text: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(text);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
}

export function TransformationEvidenceViewer(props: Props) {
  const {
    runId,
    stageId,
    expectedStateVersion,
    connectionStatus,
    workflowEvents,
    onAuthoritativeRefresh,
  } = props;
  const [viewState, setViewState] = useState<ViewState>("loading");
  const [evidence, setEvidence] = useState<TransformationEvidenceResponse | null>(null);
  const [activeTab, setActiveTab] = useState<"diff" | "package" | "risk" | "migrations" | "builder" | "forbidden">("diff");
  const [riskFilter, setRiskFilter] = useState<string>("all");
  const [error, setError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [diffSearchQuery, setDiffSearchQuery] = useState<string>("");
  const [diffContent, setDiffContent] = useState<string>("");
  const [patchIntegrityValid, setPatchIntegrityValid] = useState<boolean | null>(null);
  const fetchInFlight = useRef(false);
  const evidenceRef = useRef(evidence);
  useEffect(() => { evidenceRef.current = evidence; }, [evidence]);
  const idempotencyKeyRef = useRef(`tev-${runId}-${stageId}`);

  const fetchEvidence = useCallback(async () => {
    if (fetchInFlight.current) return;
    fetchInFlight.current = true;
    try {
      const result = await getTransformationEvidence(runId, stageId);
      setEvidence(result);
      setViewState(viewStateFromIntegrity(result.integrity_status, result.evidence_complete));
    } catch (err: unknown) {
      if (err instanceof ApiClientError && err.status === 404) {
        if (evidenceRef.current) {
          setViewState("missing-artifact");
        } else {
          setEvidence(null);
          setViewState("empty");
        }
      } else if (err instanceof ApiClientError && err.status === 409) {
        setViewState("stale");
      } else {
        setError(err instanceof Error ? err.message : "Failed to fetch evidence");
        setViewState("failure");
      }
    } finally {
      fetchInFlight.current = false;
    }
  }, [runId, stageId]);

  useEffect(() => {
    fetchEvidence();
  }, [fetchEvidence]);

  useEffect(() => {
    if (connectionStatus === "reconnecting" || connectionStatus === "recovering") {
      setViewState("reconnecting");
      fetchEvidence();
    }
  }, [connectionStatus, fetchEvidence]);

  const unifiedDiffArtifact = useMemo(() => {
    if (!evidence?.artifacts) return null;
    return evidence.artifacts.find((a: TransformationArtifactRef) => a.kind === "unified_diff") || null;
  }, [evidence]);

  useEffect(() => {
    if (!unifiedDiffArtifact) return;
    let cancelled = false;
    getArtifactById(unifiedDiffArtifact.artifact_id)
      .then(async (response) => {
        if (cancelled) return;
        const receivedChecksum = await sha256Hex(response.content);
        const expected = unifiedDiffArtifact.checksum.replace(/^sha256:/, "");
        const valid = receivedChecksum === expected;
        setPatchIntegrityValid(valid);
        if (valid) {
          setDiffContent(response.content);
        } else {
          setDiffContent("");
          setViewState("failure");
        }
      })
      .catch(() => {
        if (cancelled) return;
        setPatchIntegrityValid(false);
      });
    return () => { cancelled = true; };
  }, [unifiedDiffArtifact]);

  const prevWorkflowEventsLen = useRef(workflowEvents?.length ?? 0);
  useEffect(() => {
    const currentLen = workflowEvents?.length ?? 0;
    if (currentLen > prevWorkflowEventsLen.current) {
      const latest = workflowEvents?.[currentLen - 1];
      if (latest && (
        latest.event_type.includes("EVIDENCE") ||
        latest.event_type.includes("DIFF") ||
        latest.event_type.includes("RISK") ||
        latest.event_type.includes("REFRESH")
      )) {
        fetchEvidence();
      }
    }
    prevWorkflowEventsLen.current = currentLen;
  }, [workflowEvents, fetchEvidence]);

  const handleGenerate = async () => {
    try {
      setViewState("running");
      const result = await generateTransformationEvidence(runId, stageId, {
        expected_state_version: expectedStateVersion,
        idempotency_key: idempotencyKeyRef.current,
        correlation_id: idempotencyKeyRef.current,
      });
      setEvidence(result);
      setViewState(viewStateFromIntegrity(result.integrity_status, result.evidence_complete));
    } catch (err: unknown) {
      setViewState("failure");
      setError(err instanceof Error ? err.message : "Failed to generate evidence");
    }
  };

  const allFiles = useMemo(() => {
    if (!evidence?.diff_summary?.changed_files) return [];
    return evidence.diff_summary.changed_files as ChangedFileEntry[];
  }, [evidence]);

  const riskCounts = useMemo(() => {
    if (!evidence?.diff_summary?.files_by_classification) return {};
    return evidence.diff_summary.files_by_classification as Record<string, number>;
  }, [evidence]);

  const filteredFiles = useMemo(() => {
    if (riskFilter === "all") return allFiles;
    return allFiles.filter((f) => f.classification === riskFilter);
  }, [allFiles, riskFilter]);

  const visibleFiles = useMemo(() => {
    return filteredFiles.slice(0, MAX_VISIBLE_FILES);
  }, [filteredFiles]);

  const hiddenHighRiskCount = useMemo(() => {
    if (riskFilter === "all") return 0;
    return allFiles.filter(
      (f) => (f.classification === "high_risk" || f.classification === "sensitive") && f.classification !== riskFilter,
    ).length;
  }, [allFiles, riskFilter]);

  const isLargeDiff = evidence !== null && (evidence.total_files_changed ?? 0) > MAX_VISIBLE_FILES;
  const filteredOutCount = filteredFiles.length - visibleFiles.length;

  const packageData = evidence?.package_change as PackageChangeSummary | undefined;

  const integrityInfo = evidence ? INTEGRITY_LABELS[evidence.integrity_status] : null;

  if (viewState === "loading") {
    return (
      <div aria-label="Loading evidence" className="tev-panel p-4 border rounded-lg">
        <div className="animate-pulse space-y-3">
          <div className="h-4 bg-gray-200 rounded w-1/3" />
          <div className="h-8 bg-gray-200 rounded w-full" />
          <div className="h-8 bg-gray-200 rounded w-2/3" />
        </div>
      </div>
    );
  }

  return (
    <div className="tev-panel p-4 border rounded-lg space-y-4" role="region" aria-label="Transformation Evidence Viewer">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Transformation Evidence</h3>
        <div className="flex items-center gap-2" role="status">
          {evidence?.idempotent_replay && (
            <span className="px-2 py-0.5 bg-purple-100 text-purple-700 text-xs rounded-full" aria-label="Idempotent replay">
              Idempotent replay
            </span>
          )}
          {integrityInfo && (
            <span className={`px-2 py-0.5 text-xs rounded-full bg-gray-100 ${integrityInfo.color}`}>
              {integrityInfo.label}
            </span>
          )}
          <StatusPill value={STATUS_PILL_MAP[viewState]} />
        </div>
      </div>

      {viewState === "reconnecting" && (
        <div className="p-2 bg-amber-50 border border-amber-200 rounded text-sm text-amber-700 animate-pulse" role="alert">
          Reconnecting to backend...
        </div>
      )}

      {viewState === "missing-artifact" && (
        <div className="p-3 bg-yellow-50 border border-yellow-200 rounded text-sm" role="alert">
          <p className="text-yellow-700 font-medium">Evidence artifacts not found</p>
          <button
            onClick={fetchEvidence}
            className="mt-2 px-3 py-1 bg-yellow-600 text-white rounded hover:bg-yellow-700 text-xs"
          >
            Retry
          </button>
        </div>
      )}

      {evidence && (
        <>
          <div className="grid grid-cols-4 gap-3 p-3 bg-gray-50 rounded text-sm" role="list">
            <div role="listitem">
              <span className="text-gray-500">Files changed</span>
              <p className="font-mono font-bold">{evidence.total_files_changed}</p>
            </div>
            <div role="listitem">
              <span className="text-gray-500">Risk level</span>
              <p className={`font-mono font-bold ${
                evidence.overall_risk_level === "critical" ? "text-red-600"
                : evidence.overall_risk_level === "high" ? "text-orange-600"
                : evidence.overall_risk_level === "medium" ? "text-amber-600"
                : "text-green-600"
              }`}>
                {evidence.overall_risk_level.toUpperCase()}
              </p>
            </div>
            <div role="listitem">
              <span className="text-gray-500">Forbidden</span>
              <p className="font-mono font-bold">{evidence.forbidden_changes.length}</p>
            </div>
            <div role="listitem">
              <span className="text-gray-500">Checksum</span>
              <p className="font-mono text-xs truncate">{evidence.diff_checksum.slice(0, 16)}…</p>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3 p-3 bg-gray-50 rounded text-sm">
            {evidence.evidence_id && (
              <div>
                <span className="text-gray-500">Evidence ID</span>
                <p className="font-mono text-xs truncate">{evidence.evidence_id}</p>
              </div>
            )}
            {evidence.correlation_id && (
              <div>
                <span className="text-gray-500">Correlation ID</span>
                <p className="font-mono text-xs truncate">{evidence.correlation_id}</p>
              </div>
            )}
            <div>
              <span className="text-gray-500">Run ID</span>
              <p className="font-mono text-xs truncate">{evidence.run_id}</p>
            </div>
            <div>
              <span className="text-gray-500">Stage ID</span>
              <p className="font-mono text-xs truncate">{evidence.stage_id}</p>
            </div>
          </div>

          <div className="flex gap-2 flex-wrap">
            {viewState === "empty" && (
              <button
                onClick={handleGenerate}
                className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
              >
                Generate Evidence
              </button>
            )}

            {evidence && (
              <select
                value={riskFilter}
                onChange={(e) => setRiskFilter(e.target.value)}
                className="px-2 py-1 border rounded text-sm"
                aria-label="Filter by risk classification"
              >
                <option value="all">All files ({evidence.total_files_changed})</option>
                {Object.entries(riskCounts).map(([key, count]) => (
                  <option key={key} value={key}>
                    {key} ({count})
                  </option>
                ))}
              </select>
            )}
          </div>

          {hiddenHighRiskCount > 0 && (
            <div className="p-2 bg-amber-50 border border-amber-200 rounded text-sm text-amber-700" role="alert">
              Filter hides {hiddenHighRiskCount} high-risk finding(s)
            </div>
          )}

          <div className="border-b">
            <nav className="flex gap-4 text-sm" role="tablist" aria-label="Evidence tabs">
              {(["diff", "package", "risk", "forbidden", "builder", "migrations"] as const).map((tab) => (
                <button
                  key={tab}
                  role="tab"
                  aria-selected={activeTab === tab}
                  aria-controls={`panel-${tab}`}
                  onClick={() => setActiveTab(tab)}
                  className={`pb-2 px-1 border-b-2 transition-colors ${
                    activeTab === tab
                      ? "border-blue-500 text-blue-600 font-medium"
                      : "border-transparent text-gray-500 hover:text-gray-700"
                  }`}
                >
                  {tab === "diff" && "Diff View"}
                  {tab === "package" && "Package Changes"}
                  {tab === "risk" && "Risk Report"}
                  {tab === "forbidden" && "Forbidden"}
                  {tab === "builder" && "Builder"}
                  {tab === "migrations" && "Migrations"}
                </button>
              ))}
            </nav>
          </div>

          <div role="tabpanel" id={`panel-${activeTab}`} aria-label={activeTab}>
            {activeTab === "diff" && (
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                <div className="lg:col-span-1">
                  <TransformationFileTree
                    files={allFiles}
                    selectedFile={selectedFile}
                    onSelectFile={setSelectedFile}
                    searchQuery={diffSearchQuery}
                    filterClassification={riskFilter === "all" ? "" : riskFilter}
                  />
                </div>
                <div className="lg:col-span-2 space-y-2">
                  <div className="flex gap-2 items-center">
                    <input
                      type="text"
                      value={diffSearchQuery}
                      onChange={(e) => setDiffSearchQuery(e.target.value)}
                      placeholder="Search diff lines…"
                      aria-label="Search diff lines"
                      className="flex-1 px-2 py-1.5 text-sm border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-400"
                    />
                    {patchIntegrityValid === false && (
                      <span className="px-2 py-1 text-xs bg-red-100 text-red-700 rounded" role="alert">
                        Patch integrity check failed
                      </span>
                    )}
                    {patchIntegrityValid === true && (
                      <span className="px-2 py-1 text-xs bg-green-100 text-green-700 rounded">
                        Verified
                      </span>
                    )}
                  </div>
                  {diffContent ? (
                    <UnifiedDiffViewer
                      content={diffContent}
                      selectedFile={selectedFile}
                      searchQuery={diffSearchQuery}
                    />
                  ) : (
                    <div className="text-center py-8 text-gray-400 text-sm">
                      {patchIntegrityValid === false
                        ? "Patch artifact integrity verification failed"
                        : "Loading patch content..."}
                    </div>
                  )}
                  {filteredOutCount > 0 && (
                    <div className="p-2 bg-amber-50 text-amber-700 text-xs rounded" role="alert">
                      Showing {visibleFiles.length} of {filteredFiles.length} files. Use filter to narrow results.
                    </div>
                  )}
                  {isLargeDiff && filteredFiles.length <= MAX_VISIBLE_FILES && (
                    <div className="p-2 bg-amber-50 text-amber-700 text-xs rounded" role="alert">
                      Large diff ({evidence.total_files_changed} files) — showing summary only
                    </div>
                  )}
                  {selectedFile === null && !diffContent && visibleFiles.map((file) => (
                    <div
                      key={file.file_path}
                      className={`flex items-center justify-between p-2 rounded text-sm cursor-pointer hover:bg-gray-50 ${
                        file.classification === "sensitive" ? "bg-red-50"
                        : file.classification === "forbidden" ? "bg-red-100"
                        : file.classification === "generated" ? "bg-gray-50"
                        : file.classification === "unknown" ? "bg-yellow-50"
                        : "hover:bg-gray-50"
                      }`}
                      role="listitem"
                      onClick={() => setSelectedFile(file.file_path)}
                      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSelectedFile(file.file_path); } }}
                      tabIndex={0}
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <span className={`w-2 h-2 rounded-full flex-shrink-0 ${
                          file.classification === "sensitive" ? "bg-red-500"
                          : file.classification === "high_risk" ? "bg-orange-500"
                          : file.classification === "medium_risk" ? "bg-amber-500"
                          : file.classification === "unknown" ? "bg-yellow-500"
                          : "bg-green-500"
                        }`} />
                        <span className="truncate font-mono text-xs">{file.file_path}</span>
                        {file.classification === "unknown" && (
                          <span className="text-yellow-700 text-xs font-medium whitespace-nowrap">
                            [Unknown — review required]
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-3 flex-shrink-0 text-xs">
                        <span className="text-green-600">+{file.lines_added}</span>
                        <span className="text-red-600">-{file.lines_removed}</span>
                        <span className={`px-1.5 py-0.5 rounded text-xs ${
                          file.classification === "sensitive" ? "bg-red-100 text-red-700"
                          : file.classification === "unknown" ? "bg-yellow-100 text-yellow-700"
                          : "bg-gray-100 text-gray-600"
                        }`}>
                          {file.classification}
                        </span>
                      </div>
                    </div>
                  ))}
                  {visibleFiles.length === 0 && !diffContent && (
                    <p className="text-gray-400 text-sm py-4 text-center">No matching files</p>
                  )}
                </div>
              </div>
            )}

            {activeTab === "package" && (
              <div className="space-y-3 text-sm">
                {packageData ? (
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <h4 className="font-medium mb-1">Dependencies</h4>
                      <p className="text-gray-600">
                        Added: {packageData.dependencies_added?.length ?? 0}
                      </p>
                      <p className="text-gray-600">
                        Removed: {packageData.dependencies_removed?.length ?? 0}
                      </p>
                      {packageData.dependencies_updated && packageData.dependencies_updated.length > 0 && (
                        <div className="mt-2">
                          <span className="text-gray-500 text-xs">Updated:</span>
                          <ul className="list-disc list-inside">
                            {packageData.dependencies_updated.map((dep) => (
                              <li key={dep.name} className="text-gray-600 text-xs">
                                {dep.name}: {dep.from} → {dep.to}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                    <div>
                      <h4 className="font-medium mb-1">Angular</h4>
                      <p className="text-gray-600">
                        Before: {packageData.angular_version_before ?? "—"}
                      </p>
                      <p className="text-gray-600">
                        After: {packageData.angular_version_after ?? "—"}
                      </p>
                    </div>
                  </div>
                ) : (
                  <p className="text-gray-400 py-4 text-center">No package changes available</p>
                )}
              </div>
            )}

            {activeTab === "risk" && (
              <div className="space-y-2 text-sm">
                {evidence.forbidden_changes.length > 0 ? (
                  evidence.forbidden_changes.map((fc, idx) => (
                    <div key={idx} className="p-2 bg-red-50 border border-red-200 rounded">
                      <p className="font-medium text-red-700">
                        {(fc as unknown as ForbiddenChangeEntry).file_path}
                      </p>
                      <p className="text-red-600">{(fc as unknown as ForbiddenChangeEntry).reason}</p>
                      {(fc as unknown as ForbiddenChangeEntry).suggestion ? (
                        <p className="text-amber-700 text-xs mt-1">
                          Suggestion: {(fc as unknown as ForbiddenChangeEntry).suggestion}
                        </p>
                      ) : null}
                    </div>
                  ))
                ) : (
                  <p className="text-gray-400 py-4 text-center">No forbidden changes detected</p>
                )}
              </div>
            )}

            {activeTab === "forbidden" && (
              <div className="space-y-2 text-sm">
                {evidence.forbidden_changes.length > 0 ? (
                  evidence.forbidden_changes.map((fc, idx) => (
                    <div key={idx} className="p-2 bg-red-50 border border-red-200 rounded">
                      <p className="font-medium text-red-700">
                        {(fc as unknown as ForbiddenChangeEntry).file_path}
                      </p>
                      <p className="text-red-600">{(fc as unknown as ForbiddenChangeEntry).reason}</p>
                      {(fc as unknown as ForbiddenChangeEntry).suggestion ? (
                        <p className="text-amber-700 text-xs mt-1">
                          Suggestion: {(fc as unknown as ForbiddenChangeEntry).suggestion}
                        </p>
                      ) : null}
                    </div>
                  ))
                ) : (
                  <p className="text-gray-400 py-4 text-center">No forbidden changes detected</p>
                )}
              </div>
            )}

            {activeTab === "builder" && (
              <div className="space-y-2 text-sm">
                {evidence.builder_comparison && Object.keys(evidence.builder_comparison).length > 0 ? (
                  <>
                    <p className="text-gray-500">
                      Drift detected: {String(evidence.builder_comparison.drift_detected ?? false)}
                    </p>
                    {Array.isArray(evidence.builder_comparison.changes) && evidence.builder_comparison.changes.length > 0 ? (
                      <ul className="list-disc list-inside space-y-1">
                        {(evidence.builder_comparison.changes as Array<Record<string, unknown>>).map((c, i) => (
                          <li key={i} className="font-mono text-xs">
                            {String(c.project ?? "")}/{String(c.target ?? "")}: {String(c.before_builder ?? "—")} → {String(c.after_builder ?? "—")}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-gray-400">No builder changes</p>
                    )}
                  </>
                ) : (
                  <p className="text-gray-400 py-4 text-center">No builder comparison data</p>
                )}
              </div>
            )}

            {activeTab === "migrations" && (
              <div className="space-y-2 text-sm">
                {evidence.migration_list.length > 0 ? (
                  <ul className="list-disc list-inside space-y-1">
                    {evidence.migration_list.map((migration) => (
                      <li key={migration} className="font-mono text-xs text-gray-700">
                        {migration}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-gray-400 py-4 text-center">No migrations recorded</p>
                )}
              </div>
            )}
          </div>
        </>
      )}

      {!evidence && viewState === "empty" && (
        <div className="text-center py-8">
          <p className="text-gray-500 mb-4">No evidence has been generated yet.</p>
          <button
            onClick={handleGenerate}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
            aria-label="Generate Evidence"
          >
            Generate Evidence
          </button>
        </div>
      )}

      {!evidence && viewState === "running" && (
        <div className="text-center py-8">
          <div className="animate-spin h-8 w-8 border-4 border-blue-500 border-t-transparent rounded-full mx-auto mb-2" />
          <p className="text-gray-500">Generating evidence...</p>
        </div>
      )}

      {viewState === "failure" && error && (
        <div className="p-2 bg-red-50 border border-red-200 rounded text-sm text-red-700" role="alert">
          {error}
        </div>
      )}

      {evidence && viewState === "stale" && (
        <div className="p-2 bg-amber-50 border border-amber-200 rounded text-sm text-amber-700 flex items-center justify-between" role="alert">
          <span>{evidence.stale_reason ?? "Evidence is stale — refresh"}</span>
          <div className="flex gap-2">
            <button
              onClick={fetchEvidence}
              className="px-3 py-1 bg-amber-600 text-white rounded hover:bg-amber-700 text-xs"
            >
              Refresh
            </button>
            {onAuthoritativeRefresh && (
              <button
                onClick={onAuthoritativeRefresh}
                className="px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 text-xs"
              >
                Reconnect
              </button>
            )}
          </div>
        </div>
      )}

      {evidence && viewState === "blocked" && evidence.block_reason && (
        <div className="p-2 bg-amber-50 border border-amber-200 rounded text-sm text-amber-700" role="alert">
          {evidence.block_reason}
        </div>
      )}

      {evidence && evidence.artifacts && evidence.artifacts.length > 0 && (
        <div className="space-y-2 text-sm" role="list" aria-label="Artifact refs">
          <span className="text-gray-500 font-medium">Artifacts:</span>
          {evidence.artifacts.map((artifact) => (
            <a
              key={artifact.artifact_id}
              href={`/api/v1/artifacts/${encodeURIComponent(artifact.artifact_id)}`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 p-1.5 bg-gray-50 rounded text-xs font-mono hover:bg-gray-100 transition-colors"
              role="listitem"
            >
              <span className="px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded text-[10px] font-bold uppercase">
                {artifact.kind}
              </span>
              <span className="truncate">{artifact.relative_path}</span>
              <span className="text-gray-400 ml-auto">{artifact.checksum.slice(0, 12)}…</span>
              <span className="text-gray-400">{artifact.size_bytes} bytes</span>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
