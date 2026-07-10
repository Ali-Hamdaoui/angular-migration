import { ControlTowerShell } from "@/components/ControlTowerShell";
import { mockMigrationRun } from "@/data/mockMigrationRun";

export default async function MigrationRunPage({ params }: { params: Promise<{ runId: string }> }) {
  await params;
  return <ControlTowerShell run={mockMigrationRun} />;
}