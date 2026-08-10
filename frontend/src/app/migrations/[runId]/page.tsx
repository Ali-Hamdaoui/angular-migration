import { getAuthoritativeRunState } from "@/api/runs";
import { getMockMigrationState } from "@/api/migrations";
import { AuthoritativeRunDashboard } from "@/components/AuthoritativeRunDashboard";
import type { AuthoritativeRunStateDto, MigrationRunDto } from "@/types/generated/api";

export const dynamic = "force-dynamic";

function toAuthoritativeMockRun(run: MigrationRunDto): AuthoritativeRunStateDto {
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

export default async function MigrationRunPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  if (runId.startsWith("mock-")) {
    const mockRun = await getMockMigrationState();
    return <AuthoritativeRunDashboard runId={runId} initialState={toAuthoritativeMockRun(mockRun)} />;
  }
  try {
    const state = await getAuthoritativeRunState(runId);
    return <AuthoritativeRunDashboard runId={runId} initialState={state} />;
  } catch {
    return <main><p>Authoritative run state could not be loaded.</p></main>;
  }
}
