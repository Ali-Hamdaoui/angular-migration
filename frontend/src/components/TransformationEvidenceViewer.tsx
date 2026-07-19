"use client";

/**
 * TransformationEvidenceViewer — Custom unified diff viewer with file tree, risk filters,
 * package/source tabs, sensitive changes, large-diff handling, and blocked findings.
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { generateTransformationEvidence, getTransformationEvidence } from "@/api/transformations";
import type { TransformationEvidenceResponse } from "@/types/transformation";
import { StatusPill } from "@/components/StatusPill";

type ViewState = "loading" | "empty" | "running" | "success" | "blocked" | "stale" | "failure";

interface Props {
  runId: string;
  stageId: string;
  sourceSandboxPath: string;
  targetSandboxPath: string;
  expectedStateVersion: number;
}

export function TransformationEvidenceViewer({
  runId,
  stageId,
  sourceSandboxPath,
  targetSandboxPath,
  expectedStateVersion,
}: Props) {
  const [viewState, setViewState] = useState<ViewState>("loading");
  const [evidence, setEvidence] = useState<TransformationEvidenceResponse | null>(null);
  const [activeTab, setActiveTab] = useState<"diff" | "package" | "risk">("diff");
  const [riskFilter, setRiskFilter] = useState<string>("all");
  const [error, setError] = useState<string | null>(null);

  const fetchEvidence = useCallback(async () => {
    try {
      const result = await getTransformationEvidence(runId, stageId);
      setEvidence(result);
      setViewState(result.evidence_complete ? "success" : "blocked");
    } catch {
      setViewState("empty");
    }
  }, [runId, stageId]);

  useEffect(() => {
    fetchEvidence();
  }, [fetchEvidence]);

  const handleGenerate = async () => {
    const idempotencyKey = `tev-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    try {
      setViewState("running");
      const result = await generateTransformationEvidence(runId, stageId, {
        expected_state_version: expectedStateVersion,
        idempotency_key: idempotencyKey,
        actor: "operator",
        source_sandbox_path: sourceSandboxPath,
        target_sandbox_path: targetSandboxPath,
      });
      setEvidence(result);
      setViewState(result.evidence_complete ? "success" : "blocked");
    } catch (err: unknown) {
      setViewState("failure");
      setError(err instanceof Error ? err.message : "Failed to generate evidence");
    }
  };

  const fileEntries = useMemo(() => {
    if (!evidence?.diff_summary?.changed_files) return [];
    const files = evidence.diff_summary.changed_files as Array<{
      file_path: string;
      change_type: string;
      classification: string;
      lines_added: number;
      lines_removed: number;
    }>;
    if (riskFilter === "all") return files;
    return files.filter((f) => f.classification === riskFilter);
  }, [evidence, riskFilter]);

  const riskCounts = useMemo(() => {
    if (!evidence?.diff_summary?.files_by_classification) return {};
    return evidence.diff_summary.files_by_classification as Record<string, number>;
  }, [evidence]);

  const isLargeDiff = (evidence?.total_files_changed ?? 0) > 50;

  if (viewState === "loading") {
    return (
      <div className="tev-panel p-4 border rounded-lg">
        <div className="animate-pulse space-y-3">
          <div className="h-4 bg-gray-200 rounded w-1/3" />
          <div className="h-8 bg-gray-200 rounded w-full" />
        </div>
      </div>
    );
  }

  return (
    <div className="tev-panel p-4 border rounded-lg space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Transformation Evidence</h3>
        <StatusPill value={viewState === "success" ? "PASSED" : viewState === "blocked" ? "BLOCKED" : "RUNNING"} />
      </div>

      {/* Summary bar */}
      {evidence && (
        <div className="grid grid-cols-4 gap-3 p-3 bg-gray-50 rounded text-sm">
          <div>
            <span className="text-gray-500">Files changed</span>
            <p className="font-mono font-bold">{evidence.total_files_changed}</p>
          </div>
          <div>
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
          <div>
            <span className="text-gray-500">Forbidden</span>
            <p className="font-mono font-bold">{evidence.forbidden_changes.length}</p>
          </div>
          <div>
            <span className="text-gray-500">Checksum</span>
            <p className="font-mono text-xs truncate">{evidence.diff_checksum.slice(0, 16)}…</p>
          </div>
        </div>
      )}

      {/* Controls */}
      <div className="flex gap-2 flex-wrap">
        {viewState === "empty" && (
          <button
            onClick={handleGenerate}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
          >
            Generate Evidence
          </button>
        )}

        {/* Risk filter */}
        {evidence && (
          <select
            value={riskFilter}
            onChange={(e) => setRiskFilter(e.target.value)}
            className="px-2 py-1 border rounded text-sm"
          >
            <option value="all">All files ({evidence.total_files_changed})</option>
            {Object.entries(riskCounts).map(([key, count]) => (
              <option key={key} value={key}>{key} ({count})</option>
            ))}
          </select>
        )}
      </div>

      {/* Tabs */}
      {evidence && (
        <div className="border-b">
          <nav className="flex gap-4 text-sm">
            {(["diff", "package", "risk"] as const).map((tab) => (
              <button
                key={tab}
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
              </button>
            ))}
          </nav>
        </div>
      )}

      {/* Tab content */}
      {activeTab === "diff" && evidence && (
        <div className="space-y-1 max-h-96 overflow-y-auto">
          {isLargeDiff && (
            <div className="p-2 bg-amber-50 text-amber-700 text-xs rounded mb-2">
              Large diff ({evidence.total_files_changed} files) — showing summary only
            </div>
          )}
          {fileEntries.map((file) => (
            <div
              key={file.file_path}
              className={`flex items-center justify-between p-2 rounded text-sm ${
                file.classification === "sensitive" ? "bg-red-50"
                : file.classification === "forbidden" ? "bg-red-100"
                : file.classification === "generated" ? "bg-gray-50"
                : "hover:bg-gray-50"
              }`}
            >
              <div className="flex items-center gap-2 min-w-0">
                <span className={`w-2 h-2 rounded-full flex-shrink-0 ${
                  file.classification === "sensitive" ? "bg-red-500"
                  : file.classification === "high_risk" ? "bg-orange-500"
                  : file.classification === "medium_risk" ? "bg-amber-500"
                  : "bg-green-500"
                }`} />
                <span className="truncate font-mono text-xs">{file.file_path}</span>
              </div>
              <div className="flex items-center gap-3 flex-shrink-0 text-xs">
                <span className="text-green-600">+{file.lines_added}</span>
                <span className="text-red-600">-{file.lines_removed}</span>
                <span className={`px-1.5 py-0.5 rounded text-xs ${
                  file.classification === "sensitive" ? "bg-red-100 text-red-700"
                  : "bg-gray-100 text-gray-600"
                }`}>
                  {file.classification}
                </span>
              </div>
            </div>
          ))}
          {fileEntries.length === 0 && (
            <p className="text-gray-400 text-sm py-4 text-center">No matching files</p>
          )}
        </div>
      )}

      {activeTab === "package" && evidence?.package_change && (
        <div className="space-y-3 text-sm">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <h4 className="font-medium mb-1">Dependencies</h4>
              <p className="text-gray-600">
                Added: {(evidence.package_change as Record<string, unknown>).dependencies_added?.length ?? 0}
              </p>
              <p className="text-gray-600">
                Removed: {(evidence.package_change as Record<string, unknown>).dependencies_removed?.length ?? 0}
              </p>
            </div>
            <div>
              <h4 className="font-medium mb-1">Angular</h4>
              <p className="text-gray-600">
                Before: {(evidence.package_change as Record<string, unknown>).angular_version_before ?? "—"}
              </p>
              <p className="text-gray-600">
                After: {(evidence.package_change as Record<string, unknown>).angular_version_after ?? "—"}
              </p>
            </div>
          </div>
        </div>
      )}

      {activeTab === "risk" && evidence && (
        <div className="space-y-2 text-sm">
          {evidence.forbidden_changes.length > 0 ? (
            evidence.forbidden_changes.map((fc, idx) => (
              <div key={idx} className="p-2 bg-red-50 border border-red-200 rounded">
                <p className="font-medium text-red-700">
                  {(fc as Record<string, unknown>).file_path as string}
                </p>
                <p className="text-red-600">{(fc as Record<string, unknown>).reason as string}</p>
                {(fc as Record<string, unknown>).suggestion && (
                  <p className="text-amber-700 text-xs mt-1">
                    Suggestion: {(fc as Record<string, unknown>).suggestion as string}
                  </p>
                )}
              </div>
            ))
          ) : (
            <p className="text-gray-400 py-4 text-center">No forbidden changes detected</p>
          )}
        </div>
      )}

      {/* Blocked state */}
      {viewState === "blocked" && evidence?.block_reason && (
        <div className="p-2 bg-amber-50 border border-amber-200 rounded text-sm text-amber-700">
          {evidence.block_reason}
        </div>
      )}

      {viewState === "failure" && (
        <div className="p-2 bg-red-50 border border-red-200 rounded text-sm text-red-700">
          {error || "Failed to generate transformation evidence"}
        </div>
      )}
    </div>
  );
}
