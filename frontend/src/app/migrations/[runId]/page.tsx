import { getMockMigrationState } from "@/api/migrations";
import { RunDashboard } from "@/components/RunDashboard";

export const dynamic = "force-dynamic";

export default async function MigrationRunPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  const run = await getMockMigrationState();
  return <RunDashboard runId={runId} initialRun={run} />;
}
