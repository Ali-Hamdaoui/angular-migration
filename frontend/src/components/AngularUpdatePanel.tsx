"use client";

/**
 * AngularUpdatePanel — Angular update step with exact versions, live logs, migration list,
 * prompt blocker, and target verification matrix.
 */

import React, { useCallback, useEffect, useState } from "react";
import { startAngularUpdate, getAngularUpdate, getTargetVersion } from "@/api/transformations";
import type { AngularUpdateResponse } from "@/types/transformation";
import { StatusPill } from "@/components/StatusPill";
import { LogViewer } from "@/components/LogViewer";

type ViewState = "loading" | "empty" | "running" | "success" | "blocked" | "stale" | "reconnecting" | "failure";

interface Props {
  runId: string;
  stageId: string;
  sourceVersion: string;
  targetVersion: string;
  expectedStateVersion: number;
  onStateChange?: (newVersion: number) => void;
}

export function AngularUpdatePanel({
  runId,
  stageId,
  sourceVersion,
  targetVersion,
  expectedStateVersion,
  onStateChange,
}: Props) {
  const [viewState, setViewState] = useState<ViewState>("loading");
  const [updateResult, setUpdateResult] = useState<AngularUpdateResponse | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const fetchState = useCallback(async () => {
    try {
      setViewState("reconnecting");
      const result = await getAngularUpdate(runId, stageId);
      setUpdateResult(result);
      if (result.status === "succeeded") {
        setViewState("success");
      } else if (result.status === "failed") {
        setViewState("failure");
        setError(result.error_message ?? "Angular update failed");
      } else if (result.status === "running") {
        setViewState("running");
      } else if (result.status === "interactive_blocked") {
        setViewState("blocked");
      } else {
        setViewState("empty");
      }
    } catch {
      setViewState("empty");
    }
  }, [runId, stageId]);

  useEffect(() => {
    fetchState();
  }, [fetchState]);

  const handleStartUpdate = async () => {
    const idempotencyKey = `ang-upd-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    try {
      setViewState("running");
      setLogs((prev) => [...prev, `[${new Date().toISOString()}] Starting Angular update: ${sourceVersion} → ${targetVersion}`]);
      const result = await startAngularUpdate(runId, stageId, {
        expected_state_version: expectedStateVersion,
        idempotency_key: idempotencyKey,
        actor: "operator",
        source_version: sourceVersion,
        target_version: targetVersion,
      });
      setUpdateResult(result);
      if (result.status === "succeeded") {
        setViewState("success");
        setLogs((prev) => [...prev, `[${new Date().toISOString()}] Angular update completed successfully`]);
      } else if (result.status === "failed") {
        setViewState("failure");
        setError(result.error_message ?? "Update failed");
        setLogs((prev) => [...prev, `[${new Date().toISOString()}] Angular update failed: ${result.error_message}`]);
      } else {
        setViewState("running");
      }
      onStateChange?.(result.state_version);
    } catch (err: unknown) {
      setViewState("failure");
      const message = err instanceof Error ? err.message : "Failed to start Angular update";
      setError(message);
      setLogs((prev) => [...prev, `[${new Date().toISOString()}] Error: ${message}`]);
    }
  };

  const handleVerifyTarget = async () => {
    try {
      const result = await getTargetVersion(runId, stageId);
      setUpdateResult(result);
      if (result.target_version_status === "verified") {
        setLogs((prev) => [...prev, `[${new Date().toISOString()}] Target version verified: ${result.resolved_target_version}`]);
      } else {
        setLogs((prev) => [...prev, `[${new Date().toISOString()}] Target version mismatch detected`]);
      }
    } catch (err: unknown) {
      setLogs((prev) => [...prev, `[${new Date().toISOString()}] Version check failed: ${err instanceof Error ? err.message : "Unknown error"}`]);
    }
  };

  if (viewState === "loading") {
    return (
      <div className="angular-update-panel p-4 border rounded-lg">
        <div className="animate-pulse space-y-3">
          <div className="h-4 bg-gray-200 rounded w-1/3" />
          <div className="h-8 bg-gray-200 rounded w-1/2" />
          <div className="h-4 bg-gray-200 rounded w-2/3" />
        </div>
      </div>
    );
  }

  return (
    <div className="angular-update-panel p-4 border rounded-lg space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Angular Update</h3>
        <StatusPill status={viewState === "success" ? "PASSED" : viewState === "failure" ? "FAILED" : "RUNNING"} />
      </div>

      {/* Version matrix */}
      <div className="grid grid-cols-2 gap-4 p-3 bg-gray-50 rounded">
        <div>
          <span className="text-sm text-gray-500">Source</span>
          <p className="font-mono text-sm">{sourceVersion}</p>
        </div>
        <div>
          <span className="text-sm text-gray-500">Target</span>
          <p className="font-mono text-sm">{targetVersion}</p>
        </div>
        {updateResult?.resolved_target_version && (
          <div className="col-span-2">
            <span className="text-sm text-gray-500">Resolved target</span>
            <p className="font-mono text-sm font-bold text-green-600">
              {updateResult.resolved_target_version}
              {updateResult.target_version_status === "verified" && " ✓"}
            </p>
          </div>
        )}
      </div>

      {/* Action controls */}
      <div className="flex gap-2">
        {viewState === "empty" && (
          <button
            onClick={handleStartUpdate}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
            disabled={!sourceVersion || !targetVersion}
          >
            Start Angular Update
          </button>
        )}
        {viewState === "success" && (
          <button
            onClick={handleVerifyTarget}
            className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700"
          >
            Verify Target Version
          </button>
        )}
        {viewState === "failure" && (
          <div className="text-red-600 text-sm p-2 bg-red-50 rounded">
            {error || "Update failed. Review logs for details."}
          </div>
        )}
        {viewState === "blocked" && (
          <div className="text-amber-600 text-sm p-2 bg-amber-50 rounded">
            Interactive prompt detected. Manual intervention required.
          </div>
        )}
      </div>

      {/* Live logs */}
      {logs.length > 0 && (
        <div>
          <h4 className="text-sm font-medium mb-1">Logs</h4>
          <LogViewer lines={logs} maxHeight={200} />
        </div>
      )}

      {/* Stale state warning */}
      {viewState === "stale" && (
        <div className="p-2 bg-amber-50 border border-amber-200 rounded text-sm text-amber-700">
          State version changed. Reloading snapshot...
        </div>
      )}
    </div>
  );
}
