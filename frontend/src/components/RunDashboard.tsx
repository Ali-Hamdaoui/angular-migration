"use client";

import { useMemo } from "react";
import type { MigrationRunDto } from "@/types/generated/api";
import { useMigrationEvents } from "@/hooks/useMigrationEvents";
import { applyEventToRun } from "@/hooks/applyEventToRun";
import { ControlTowerShell } from "./ControlTowerShell";
import { ConnectionStatusBar } from "./ConnectionStatusBar";
import { EventStreamPanel } from "./EventStreamPanel";

export function RunDashboard({ runId, initialRun }: { runId: string; initialRun: MigrationRunDto }) {
  const { status, events } = useMigrationEvents(runId);

  const run = useMemo(() => {
    return events.reduce(applyEventToRun, initialRun);
  }, [initialRun, events]);

  return (
    <>
      <ConnectionStatusBar status={status} />
      <ControlTowerShell run={run} />
      <EventStreamPanel events={events} />
    </>
  );
}
