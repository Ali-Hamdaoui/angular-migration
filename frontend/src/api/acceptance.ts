"use client";

import type {
  ArtifactRefDto,
  HarnessEvaluateRequestDto,
  HarnessRequestDto,
  HarnessResultDto,
  HarnessRunStatusDto,
  HarnessStatusDto,
} from "@/types/generated/api";
import { createApiClient } from "@/api/client";

const client = createApiClient();

/** Fetch the current acceptance suite status. */
export async function getAcceptanceStatus(
  fetchClient = client,
): Promise<HarnessStatusDto> {
  return fetchClient.get("/operator/acceptance-suite/status");
}

/** Generate a new acceptance fixture. */
export async function createAcceptanceFixture(
  request: HarnessRequestDto,
  fetchClient = client,
): Promise<HarnessResultDto> {
  return fetchClient.post("/operator/acceptance-suite/fixtures", request);
}

/** Evaluate a previously generated fixture. */
export async function evaluateAcceptanceFixture(
  request: HarnessEvaluateRequestDto,
  fetchClient = client,
): Promise<HarnessResultDto> {
  return fetchClient.post(
    "/operator/acceptance-suite/fixtures/evaluate",
    request,
  );
}

/** List all harness run IDs with evidence metadata. */
export async function listHarnessRuns(
  fetchClient = client,
): Promise<{ run_id: string; artifact_count: number; latest_event: string | null }[]> {
  return fetchClient.get("/operator/acceptance-suite/runs");
}

/** Get full details for a specific harness run. */
export async function getHarnessRun(
  runId: string,
  fetchClient = client,
): Promise<HarnessRunStatusDto> {
  return fetchClient.get(
    `/operator/acceptance-suite/runs/${encodeURIComponent(runId)}`,
  );
}

/** Get all evidence artifact refs for a harness run. */
export async function getHarnessRunEvidence(
  runId: string,
  fetchClient = client,
): Promise<ArtifactRefDto[]> {
  return fetchClient.get(
    `/operator/acceptance-suite/runs/${encodeURIComponent(runId)}/evidence`,
  );
}
