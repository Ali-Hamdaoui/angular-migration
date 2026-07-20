import { getAuthoritativeRunState } from "@/api/runs";
import { getMigrationState, getMockMigrationState } from "@/api/migrations";
import { AuthoritativeRunDashboard } from "@/components/AuthoritativeRunDashboard";
import { RunDashboard } from "@/components/RunDashboard";

export const dynamic = "force-dynamic";

export default async function MigrationRunPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  if (runId.startsWith("mock-")) {
    const mockRun = await getMockMigrationState();
    return <RunDashboard runId={runId} initialRun={mockRun} />;
  }
  try {
    const state = await getAuthoritativeRunState(runId);
    const migration = await getMigrationState(runId).catch(() => null);
    return <AuthoritativeRunDashboard runId={runId} initialState={state} initialMigrationState={migration} />;
  } catch {
    return <main><p>Authoritative run state could not be loaded.</p></main>;
  }
}
