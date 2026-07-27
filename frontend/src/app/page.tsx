"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ApiClientError } from "@/api/client";
import { getAuthoritativeRunState } from "@/api/runs";
import { EnvironmentDiagnosticsPanel } from "@/components/EnvironmentDiagnosticsPanel";
import { AuthoritativeRunDashboard } from "@/components/AuthoritativeRunDashboard";
import type { AuthoritativeRunStateDto } from "@/types/generated/api";

export const ACTIVE_RUN_STORAGE_KEY = "amfa.activeRunId";

type RestorationState = "restoring" | "loaded" | "prepare" | "not-found" | "unavailable";

function readStoredRunId(): string | null {
  try { return window.localStorage.getItem(ACTIVE_RUN_STORAGE_KEY)?.trim() || null; } catch { return null; }
}

function writeRunUrl(runId: string | null) {
  const url = new URL(window.location.href);
  if (runId) url.searchParams.set("run_id", runId);
  else url.searchParams.delete("run_id");
  window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
}

function preparePage(notice?: string) {
  return <main className="landing"><p className="eyebrow">AI Frontend Migration Factory</p><h1>Control Tower</h1>{notice ? <p role="alert">{notice}</p> : null}<p>Review backend-owned migration state and prepare an authoritative external migration run.</p><Link className="button" href="/migrations/new">Prepare migration</Link><EnvironmentDiagnosticsPanel /></main>;
}

export default function HomePage() {
  const [restoration, setRestoration] = useState<RestorationState>("restoring");
  const [run, setRun] = useState<AuthoritativeRunStateDto | null>(null);

  const restore = useCallback(() => {
    const urlRunId = new URL(window.location.href).searchParams.get("run_id")?.trim() || null;
    const storedRunId = readStoredRunId();
    const candidate = urlRunId || storedRunId;
    if (!candidate) {
      setRun(null);
      setRestoration("prepare");
      return;
    }
    setRestoration("restoring");
    getAuthoritativeRunState(candidate).then((state) => {
      try { window.localStorage.setItem(ACTIVE_RUN_STORAGE_KEY, candidate); } catch { /* storage is optional */ }
      writeRunUrl(candidate);
      setRun(state);
      setRestoration("loaded");
    }).catch((error: unknown) => {
      if (error instanceof ApiClientError && error.status === 404) {
        try { if (readStoredRunId() === candidate) window.localStorage.removeItem(ACTIVE_RUN_STORAGE_KEY); } catch { /* storage is optional */ }
        if (urlRunId === candidate) writeRunUrl(null);
        setRun(null);
        setRestoration("not-found");
      } else {
        setRestoration("unavailable");
      }
    });
  }, []);

  useEffect(() => { restore(); }, [restore]);

  if (restoration === "restoring") return <main role="status" aria-live="polite"><p>Restoring authoritative migration…</p></main>;
  if (restoration === "loaded" && run) return <AuthoritativeRunDashboard runId={run.run_id} initialState={run} />;
  if (restoration === "unavailable") return <main role="alert"><p>The authoritative migration could not be reached. Your active run is preserved.</p><button type="button" onClick={restore}>Retry restoration</button></main>;
  if (restoration === "not-found") return preparePage("The requested migration run was not found. You can prepare a new migration.");
  return preparePage();
}
