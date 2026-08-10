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

function preparePage(notice?: string, resumeRunId?: string | null) {
  return <main className="landing">
    <p className="eyebrow">AI Frontend Migration Factory</p>
    <h1>Start a migration</h1>
    {notice ? <p role="alert">{notice}</p> : null}
    <p className="landingLead">Use four clear steps to check the project, review readiness, approve the plan, and follow the migration.</p>
    <p className="landingNote">The source stays read-only. The backend remains the authority for every decision and piece of evidence.</p>
    <div className="landingActions">
      <Link className="button" href="/migrations/new">Start a new migration</Link>
      {resumeRunId ? <Link className="secondaryButton" href={`/?run_id=${encodeURIComponent(resumeRunId)}`}>Resume active migration</Link> : null}
    </div>
    <details className="landingDiagnostics">
      <summary>View diagnostics</summary>
      <EnvironmentDiagnosticsPanel />
    </details>
  </main>;
}

export default function HomePage() {
  const [restoration, setRestoration] = useState<RestorationState>("restoring");
  const [run, setRun] = useState<AuthoritativeRunStateDto | null>(null);
  const [resumeRunId, setResumeRunId] = useState<string | null>(null);

  const restore = useCallback(() => {
    const urlRunId = new URL(window.location.href).searchParams.get("run_id")?.trim() || null;
    const storedRunId = readStoredRunId();
    const candidate = urlRunId || storedRunId;
    if (!candidate) {
      setRun(null);
      setResumeRunId(null);
      setRestoration("prepare");
      return;
    }
    setResumeRunId(candidate);
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
        setResumeRunId(null);
        setRestoration("not-found");
      } else {
        setRestoration("unavailable");
      }
    });
  }, []);

  useEffect(() => { restore(); }, [restore]);

  if (restoration === "restoring") return <main role="status" aria-live="polite"><p>Restoring authoritative migration...</p></main>;
  if (restoration === "loaded" && run) return <AuthoritativeRunDashboard runId={run.run_id} initialState={run} />;
  if (restoration === "unavailable") return <main role="alert"><p>The authoritative migration could not be reached. Your active run is preserved.</p><div className="landingActions"><button type="button" onClick={restore}>Retry restoration</button>{resumeRunId ? <Link className="secondaryButton" href={`/?run_id=${encodeURIComponent(resumeRunId)}`}>Resume active migration</Link> : null}</div></main>;
  if (restoration === "not-found") return preparePage("The requested migration run was not found. You can prepare a new migration.", resumeRunId);
  return preparePage(undefined, resumeRunId);
}
