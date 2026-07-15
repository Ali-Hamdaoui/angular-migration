"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { decideG01, getProductionPreflight } from "@/api/preflights";
import { createAuthoritativeRun, startAuthoritativeRun } from "@/api/runs";
import { usePreflightEvents } from "@/hooks/usePreflightEvents";
import type { G01Decision, ProductionPreflight } from "@/types/preflight";

export function G01ReviewPanel({ preflight, actor = "control-tower" }: { preflight: ProductionPreflight; actor?: string }) {
  const router = useRouter();
  const [current, setCurrent] = useState(preflight);
  const refresh = useCallback(() => { getProductionPreflight(preflight.snapshot.preflight_id).then(setCurrent).catch(() => undefined); }, [preflight.snapshot.preflight_id]);
  const stream = usePreflightEvents(preflight.snapshot.preflight_id, refresh);
  const { snapshot } = current;
  const [comment, setComment] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [startingRun, setStartingRun] = useState(false);
  const canApprove = snapshot.status !== "blocked" && snapshot.status !== "expired" && snapshot.status !== "stale";

  async function submit(decision: G01Decision) {
    setBusy(true);
    setMessage(null);
    try {
      const result = await decideG01(snapshot.preflight_id, {
        gate_id: snapshot.gate_id,
        decision,
        expected_state_version: snapshot.state_version,
        input_checksum: snapshot.input_checksum,
        artifact_set_checksum: snapshot.artifact_set_checksum,
        idempotency_key: `g01-${snapshot.preflight_id}-${decision}`,
        actor,
        comment: comment || null,
      });
      setCurrent((value) => ({ ...value, snapshot: { ...value.snapshot, approval_status: result.decision } }));
      setMessage(`${result.decision}${result.idempotent_replay ? " (replayed)" : ""}`);
    } catch {
      setMessage("G01 decision is stale or could not be recorded.");
    } finally {
      setBusy(false);
    }
  }

  async function handleStartAuthoritativeRun() {
    setStartingRun(true);
    setMessage(null);
    try {
      const created = await createAuthoritativeRun({
        preflight_id: snapshot.preflight_id,
        input_checksum: snapshot.input_checksum,
        artifact_set_checksum: snapshot.artifact_set_checksum,
        idempotency_key: `run-create-${snapshot.preflight_id}`,
        actor,
        client_constraints: { preserve_ui: true, preserve_behavior: true, preserve_business_logic: true, preserve_api_contracts: true, preserve_authentication_authorization: true, allow_optional_modernization: false },
        pricing_snapshot: {},
      });
      const started = await startAuthoritativeRun(created.run_id, { expected_state_version: created.state_version, idempotency_key: `run-start-${created.run_id}`, actor });
      router.push(`/migrations/${started.run_id}`);
    } catch {
      setMessage("The authoritative run could not be started. Refresh G01 evidence and retry.");
    } finally {
      setStartingRun(false);
    }
  }

  return (
    <section aria-label="G01 review">
      <h2>G01 production preflight</h2>
      <p>Status: {snapshot.status}</p><p>Event stream: {stream.status}</p><p>G01: {snapshot.approval_status}</p>
      <p>Input checksum: {snapshot.input_checksum}</p>
      <p>Evidence checksum: {snapshot.artifact_set_checksum}</p>
      {snapshot.blockers.length ? <p>Blockers: {snapshot.blockers.join(", ")}</p> : null}
      {snapshot.warnings.length ? <p>Warnings: {snapshot.warnings.join(", ")}</p> : null}
      <ul>{Object.entries(snapshot.artifacts).map(([name, artifact]) => <li key={name}>{name}: {artifact.checksum}</li>)}</ul>
      <label>Reviewer comment<textarea value={comment} onChange={(event) => setComment(event.target.value)} /></label>
      <div>
        <button type="button" disabled={busy || !canApprove} onClick={() => submit(comment ? "approved_with_comment" : "approved")}>Approve G01</button>
        <button type="button" disabled={busy} onClick={() => submit("modification_requested")}>Request modification</button>
        <button type="button" disabled={busy} onClick={() => submit("rejected")}>Reject G01</button>
      </div>
      {snapshot.approval_status === "approved" || snapshot.approval_status === "approved_with_comment" ? <button type="button" disabled={startingRun} onClick={handleStartAuthoritativeRun}>{startingRun ? "Creating authoritative run..." : "Create and start authoritative run"}</button> : null}
      {message ? <p role="status">{message}</p> : null}
    </section>
  );
}
