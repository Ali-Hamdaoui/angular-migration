import { getAuthoritativeRunState } from "@/api/runs";
import { getMockMigrationState } from "@/api/migrations";
import { ApiClientError } from "@/api/client";
import { RunDashboard } from "@/components/RunDashboard";
import { AuthoritativeRunDashboard } from "@/components/AuthoritativeRunDashboard";

export const dynamic = "force-dynamic";

export default async function MigrationRunPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  if (runId.startsWith("mock-")) {
    try {
      const mockRun = await getMockMigrationState();
      return <div className="mockWorkspace">
        <aside className="mockNotice" role="note">Demo data only. This workspace is not an authoritative migration run.</aside>
        <RunDashboard runId={runId} initialRun={mockRun} mode="mock" />
      </div>;
    } catch {
      return <main role="alert" className="routeError"><p>Demo migration data is unavailable. Try again or return to migrations.</p><div><a href={`/migrations/${encodeURIComponent(runId)}`}>Retry this migration</a><a href="/">Return to migrations</a></div></main>;
    }
  }
  try {
    const state = await getAuthoritativeRunState(runId);
    return <AuthoritativeRunDashboard runId={runId} initialState={state} />;
  } catch (error) {
    const message = error instanceof ApiClientError && error.status === 404
      ? "This migration run was not found. Return to migrations and choose another run."
      : "Authoritative run state could not be loaded. Retry from migrations.";
    return <main role="alert" className="routeError"><p>{message}</p><div><a href={`/?run_id=${encodeURIComponent(runId)}`}>Retry this migration</a><a href="/">Return to migrations</a></div></main>;
  }
}
