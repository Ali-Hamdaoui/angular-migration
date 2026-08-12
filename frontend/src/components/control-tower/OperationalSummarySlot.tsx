import type { AuthoritativeRunStateDto } from "@/types/generated/api";
import { OperationalSummary } from "./OperationalSummary";

export function OperationalSummarySlot({
  runId,
  run,
}: {
  runId: string;
  run: AuthoritativeRunStateDto;
}) {
  return <OperationalSummary runId={runId} run={run} />;
}
