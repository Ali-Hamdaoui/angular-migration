"use client";

import { useEffect, useMemo, useState } from "react";
import type { AuthoritativeRunStateDto, MigrationRunDto } from "@/types/generated/api";
import { getMigrationState } from "@/api/migrations";
import { useMigrationEvents } from "@/hooks/useMigrationEvents";
import { applyEventToRun } from "@/hooks/applyEventToRun";
import { ControlTowerShell } from "./ControlTowerShell";
import { ConnectionStatusBar } from "./ConnectionStatusBar";
import { EventStreamPanel } from "./EventStreamPanel";

/** Adapt demo data without implying that it has backend authority. */
export function adaptMockMigrationRun(run: MigrationRunDto): AuthoritativeRunStateDto {
  return {
    run_id: run.run_id,
    status: run.status,
    run_phase: run.run_phase,
    phase_status: run.phase_status,
    approval_status: run.approval_status,
    repair_status: run.repair_status,
    state_version: 1,
    preflight_id: `mock-preflight-${run.run_id}`,
    source_path: "mock://workspace/source",
    target_output_path: "mock://workspace/target",
    graph_thread_id: `mock-thread-${run.run_id}`,
    created_at: run.created_at,
    updated_at: run.updated_at,
    artifacts: run.artifacts,
    workflow_events: run.workflow_events,
  };
}

export function RunDashboard({ runId, initialRun }: { runId: string; initialRun: MigrationRunDto }) {
  const [snapshot, setSnapshot] = useState(initialRun);
  const { status, events, recoveryRequired, clearRecoveryRequired } = useMigrationEvents(runId);

  useEffect(() => {
    if (!recoveryRequired) return;
    let active = true;
    getMigrationState(runId)
      .then((nextSnapshot) => {
        if (active) setSnapshot(nextSnapshot);
      })
      .finally(() => {
        if (active) clearRecoveryRequired();
      });
    return () => {
      active = false;
    };
  }, [runId, recoveryRequired, clearRecoveryRequired]);

  const run = useMemo(() => {
    return events.reduce(applyEventToRun, snapshot);
  }, [snapshot, events]);

  return (
    <>
      <ConnectionStatusBar status={status} />
      <ControlTowerShell run={run} runId={runId} connectionStatus={status} />
      <EventStreamPanel events={events} />
    </>
  );
}
