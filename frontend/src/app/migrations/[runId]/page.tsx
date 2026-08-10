import { getAuthoritativeRunState } from "@/api/runs";
import { getMockMigrationState } from "@/api/migrations";
import { AuthoritativeRunDashboard } from "@/components/AuthoritativeRunDashboard";
import { adaptMockMigrationRun } from "@/components/RunDashboard";

export const dynamic = "force-dynamic";

export default async function MigrationRunPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  if (runId.startsWith("mock-")) {
    const mockRun = await getMockMigrationState();
    return <div className="mockWorkspace">
      <aside className="mockNotice" role="note">Demo data only. This workspace is not an authoritative migration run.</aside>
      <AuthoritativeRunDashboard runId={runId} initialState={adaptMockMigrationRun(mockRun)} />
    </div>;
  }
  try {
    const state = await getAuthoritativeRunState(runId);
    return <AuthoritativeRunDashboard runId={runId} initialState={state} />;
  } catch {
    return <main><p>Authoritative run state could not be loaded.</p></main>;
  }
}
