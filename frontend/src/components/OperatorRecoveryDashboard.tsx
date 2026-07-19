"use client";

import React, { useEffect, useState } from "react";

interface ReconciliationStatus {
  reconciliation_id: string;
  backend_instance_id: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  stale_leases_found: number;
  interrupted_commands_found: number;
  artifact_mismatches_found: number;
  recovered_runs: number;
  quarantined_runs: number;
  graph_reconstructed: boolean;
  artifacts: string[];
  errors: string[];
}

interface RunResumeRequest {
  run_id: string;
  expected_state_version: number;
  idempotency_key: string;
  actor: string;
}

/**
 * Operator Recovery Dashboard — displays startup reconciliation status
 * and provides run resume capabilities. Reads authoritative backend state only.
 */
export default function OperatorRecoveryDashboard() {
  const [reconciliation, setReconciliation] = useState<ReconciliationStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [resumeId, setResumeId] = useState<string>("");
  const [resumeState, setResumeState] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [resumeMessage, setResumeMessage] = useState<string>("");

  useEffect(() => {
    fetchLatestReconciliation();
  }, []);

  async function fetchLatestReconciliation() {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/v1/operator/reconciliation/latest");
      if (!response.ok) {
        if (response.status === 404) {
          setReconciliation(null);
          return;
        }
        throw new Error(`Failed to fetch reconciliation status: ${response.statusText}`);
      }
      const data = await response.json();
      setReconciliation(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  async function triggerReconciliation() {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/v1/operator/reconciliation", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          idempotency_key: `recon-${Date.now()}`,
          actor: "operator",
        }),
      });
      if (!response.ok) throw new Error(`Reconciliation failed: ${response.statusText}`);
      const data = await response.json();
      setReconciliation(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  async function resumeRun() {
    if (!resumeId) return;
    setResumeState("loading");
    setResumeMessage("");
    try {
      const response = await fetch(`/api/v1/runs/${resumeId}/resume`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          expected_state_version: 1,
          idempotency_key: `resume-${Date.now()}`,
          actor: "operator",
          checkpoint_valid: true,
          workspace_valid: true,
          policy_compatible: true,
        } as RunResumeRequest),
      });
      if (!response.ok) throw new Error(`Resume failed: ${response.statusText}`);
      setResumeState("success");
      setResumeMessage("Run resumed successfully");
    } catch (err) {
      setResumeState("error");
      setResumeMessage(err instanceof Error ? err.message : "Resume failed");
    }
  }

  if (loading && !reconciliation) {
    return <div className="p-4">Loading reconciliation status...</div>;
  }

  return (
    <div className="p-4 space-y-6">
      <h2 className="text-xl font-bold">Operator Recovery Dashboard</h2>

      {error && (
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded" role="alert">
          {error}
        </div>
      )}

      <button
        onClick={triggerReconciliation}
        disabled={loading}
        className="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded disabled:opacity-50"
      >
        {loading ? "Running..." : "Run Startup Reconciliation"}
      </button>

      {reconciliation && (
        <div className="bg-white shadow rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-4">Latest Reconciliation</h3>
          <dl className="grid grid-cols-2 gap-4">
            <div>
              <dt className="text-sm text-gray-500">Status</dt>
              <dd className={`font-medium ${reconciliation.status === "completed" ? "text-green-600" : "text-yellow-600"}`}>
                {reconciliation.status}
              </dd>
            </div>
            <div>
              <dt className="text-sm text-gray-500">Instance</dt>
              <dd className="font-mono text-sm">{reconciliation.backend_instance_id}</dd>
            </div>
            <div>
              <dt className="text-sm text-gray-500">Stale Leases</dt>
              <dd>{reconciliation.stale_leases_found}</dd>
            </div>
            <div>
              <dt className="text-sm text-gray-500">Interrupted Commands</dt>
              <dd>{reconciliation.interrupted_commands_found}</dd>
            </div>
            <div>
              <dt className="text-sm text-gray-500">Artifact Mismatches</dt>
              <dd>{reconciliation.artifact_mismatches_found}</dd>
            </div>
            <div>
              <dt className="text-sm text-gray-500">Recovered Runs</dt>
              <dd>{reconciliation.recovered_runs}</dd>
            </div>
            <div>
              <dt className="text-sm text-gray-500">Quarantined Runs</dt>
              <dd>{reconciliation.quarantined_runs}</dd>
            </div>
            <div>
              <dt className="text-sm text-gray-500">Graph Reconstructed</dt>
              <dd>{reconciliation.graph_reconstructed ? "Yes" : "No"}</dd>
            </div>
          </dl>
        </div>
      )}

      {!reconciliation && !loading && (
        <div className="bg-gray-100 border border-gray-300 text-gray-700 px-4 py-3 rounded">
          No reconciliation has been run yet. Click the button above to start one.
        </div>
      )}

      <div className="bg-white shadow rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4">Run Resume</h3>
        <div className="flex gap-2">
          <input
            type="text"
            value={resumeId}
            onChange={(e) => setResumeId(e.target.value)}
            placeholder="Enter run ID to resume"
            className="flex-1 border border-gray-300 rounded px-3 py-2"
            disabled={resumeState === "loading"}
          />
          <button
            onClick={resumeRun}
            disabled={!resumeId || resumeState === "loading"}
            className="bg-green-500 hover:bg-green-700 text-white font-bold py-2 px-4 rounded disabled:opacity-50"
          >
            Resume
          </button>
        </div>
        {resumeMessage && (
          <p className={`mt-2 text-sm ${resumeState === "success" ? "text-green-600" : "text-red-600"}`}>
            {resumeMessage}
          </p>
        )}
      </div>
    </div>
  );
}
