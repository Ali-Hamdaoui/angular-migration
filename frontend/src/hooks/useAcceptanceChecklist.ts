"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  createAcceptanceFixture,
  evaluateAcceptanceFixture,
  getAcceptanceStatus,
  getHarnessRun,
  getHarnessRunEvidence,
} from "@/api/acceptance";
import type {
  ArtifactRefDto,
  HarnessFixtureType,
  HarnessResultDto,
  HarnessRunStatusDto,
  HarnessStatusDto,
} from "@/types/generated/api";

/** Possible states of the acceptance-checklist polling lifecycle. */
export type ChecklistConnectionStatus =
  | "loading"
  | "idle"
  | "polling"
  | "stale"
  | "backend-failure"
  | "reconnect-required";

/** Maximum consecutive errors before declaring the backend unreachable. */
const MAX_CONSECUTIVE_ERRORS = 3;
/** Polling interval in milliseconds. */
const POLL_INTERVAL_MS = 5000;

export type UseAcceptanceChecklistResult = {
  status: ChecklistConnectionStatus;
  suiteStatus: HarnessStatusDto | null;
  runDetails: HarnessRunStatusDto | null;
  error: string | null;
  start: (fixtureType: HarnessFixtureType, name?: string) => Promise<HarnessResultDto>;
  evaluate: (fixtureId: string) => Promise<HarnessResultDto>;
  refresh: () => Promise<void>;
  evidence: ArtifactRefDto[];
};

export function useAcceptanceChecklist(
  initialStatus: HarnessStatusDto | null,
  runId: string | null,
): UseAcceptanceChecklistResult {
  const [status, setStatus] = useState<ChecklistConnectionStatus>("loading");
  const [suiteStatus, setSuiteStatus] = useState<HarnessStatusDto | null>(initialStatus);
  const [runDetails, setRunDetails] = useState<HarnessRunStatusDto | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [evidence, setEvidence] = useState<ArtifactRefDto[]>([]);

  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const consecutiveErrorsRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const prevStateVersionRef = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      const result = await getAcceptanceStatus();
      setSuiteStatus(result);
      consecutiveErrorsRef.current = 0;
      setError(null);

      // Detect stale state_version
      if (prevStateVersionRef.current !== null) {
        const latestVersion = Math.max(
          ...result.fixtures.map((f) => f.state_version),
          0,
        );
        if (latestVersion > prevStateVersionRef.current) {
          setStatus("stale");
        }
      }
      prevStateVersionRef.current = Math.max(
        ...result.fixtures.map((f) => f.state_version),
        0,
      );

      if (status === "loading") {
        setStatus("polling");
      } else if (status !== "stale") {
        setStatus("polling");
      }
    } catch {
      consecutiveErrorsRef.current += 1;
      if (consecutiveErrorsRef.current >= MAX_CONSECUTIVE_ERRORS * 2) {
        setStatus("reconnect-required");
        setError("Backend unreachable after multiple retries — reconnection required.");
      } else if (consecutiveErrorsRef.current >= MAX_CONSECUTIVE_ERRORS) {
        setStatus("backend-failure");
        setError("Backend unreachable — retrying in the background.");
      }
    }
  }, [status]);

  const start = useCallback(
    async (fixtureType: HarnessFixtureType, name?: string): Promise<HarnessResultDto> => {
      const result = await createAcceptanceFixture({
        fixture_type: fixtureType,
        name: name ?? fixtureType,
      });
      await refresh();
      setStatus("idle");
      return result;
    },
    [refresh],
  );

  const evaluate = useCallback(
    async (fixtureId: string): Promise<HarnessResultDto> => {
      const result = await evaluateAcceptanceFixture({ fixture_id: fixtureId });
      await refresh();
      setStatus("idle");
      return result;
    },
    [refresh],
  );

  // Bootstrap: initial refresh to move from "loading" to "polling"
  useEffect(() => {
    if (status === "loading") {
      void refresh();
    }
  }, [refresh, status]);

  // Polling: interval while active
  useEffect(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }

    if (status === "polling" || status === "idle") {
      pollingRef.current = setInterval(() => {
        void refresh();
      }, POLL_INTERVAL_MS);
    }

    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [status, refresh]);

  // Fetch run details when runId is set
  useEffect(() => {
    if (!runId) {
      setRunDetails(null);
      setEvidence([]);
      return;
    }

    const controller = new AbortController();
    abortRef.current = controller;

    void (async () => {
      try {
        const [details, evidenceData] = await Promise.all([
          getHarnessRun(runId),
          getHarnessRunEvidence(runId),
        ]);
        if (!controller.signal.aborted) {
          setRunDetails(details);
          setEvidence(evidenceData);
        }
      } catch {
        if (!controller.signal.aborted) {
          setRunDetails(null);
          setEvidence([]);
        }
      }
    })();

    return () => {
      controller.abort();
    };
  }, [runId]);

  return { status, suiteStatus, runDetails, error, start, evaluate, refresh, evidence };
}
