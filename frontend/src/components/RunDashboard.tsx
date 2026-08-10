"use client";

import { useEffect, useMemo, useState } from "react";
import type { MigrationRunDto } from "@/types/generated/api";
import { getMigrationState } from "@/api/migrations";
import { useMigrationEvents } from "@/hooks/useMigrationEvents";
import { applyEventToRun } from "@/hooks/applyEventToRun";
import { ControlTowerShell } from "./ControlTowerShell";
import { ConnectionStatusBar } from "./ConnectionStatusBar";
import { EventStreamPanel } from "./EventStreamPanel";

type RunDashboardProps = { runId: string; initialRun: MigrationRunDto; mode?: "authoritative" | "mock" };

export function RunDashboard({ mode = "authoritative", ...props }: RunDashboardProps) {
  if (mode === "mock") return <ControlTowerShell run={props.initialRun} mode="mock" />;
  return <LiveRunDashboard {...props} />;
}

function LiveRunDashboard({ runId, initialRun }: RunDashboardProps) {
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
