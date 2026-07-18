import { apiClient, type createApiClient } from "./client";
import type {
  CreateSourceSnapshotRequest,
  SourceSnapshotDto,
} from "@/types/generated/api";

type ApiClient = ReturnType<typeof createApiClient>;

export function createSourceSnapshot(
  runId: string,
  request: CreateSourceSnapshotRequest,
  client: ApiClient = apiClient,
): Promise<SourceSnapshotDto> {
  return client.post<SourceSnapshotDto>(
    `/api/v1/runs/${encodeURIComponent(runId)}/snapshots`,
    request,
  );
}

export function getSourceSnapshot(
  runId: string,
  snapshotId: string,
  client: ApiClient = apiClient,
): Promise<SourceSnapshotDto> {
  return client.get<SourceSnapshotDto>(
    `/api/v1/runs/${encodeURIComponent(runId)}/snapshots/${encodeURIComponent(snapshotId)}`,
  );
}
