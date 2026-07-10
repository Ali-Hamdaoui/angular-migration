import { getMockMigrationState } from "@/api/migrations";
import { ControlTowerShell } from "@/components/ControlTowerShell";

export const dynamic = "force-dynamic";

export default async function MigrationRunPage({ params }: { params: Promise<{ runId: string }> }) {
  await params;
  const run = await getMockMigrationState();
  return <ControlTowerShell run={run} />;
}