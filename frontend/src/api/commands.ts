import { apiClient, type createApiClient } from "./client";
import type {
  CommandTemplateListDto,
  CommandTemplateDto,
  CommandPolicyValidateRequestDto,
  CommandPolicyValidateResponseDto,
  CommandExecuteRequestDto,
  CommandExecutionResponseDto,
  CommandExecutionListDto,
  ArtifactRefDto,
} from "@/types/generated/api";

type ApiClient = ReturnType<typeof createApiClient>;

export type CommandArtifactMetadata = {
  artifact: ArtifactRefDto;
  content: string;
  created_by: string | null;
  content_type: string;
  filename: string | null;
};

export type CommandLogSummary = {
  execution_id: string;
  run_id: string;
  total_chunks: number;
  streams: { stdout: number; stderr: number; system: number };
  first_sequence: number | null;
  last_sequence: number | null;
  finalized: boolean;
  finalized_at: string | null;
  truncated: { stdout: boolean; stderr: boolean };
  redaction_applied: boolean;
};

export type CommandLogChunk = {
  sequence: number;
  stream: "stdout" | "stderr" | "system" | string;
  text: string;
  redacted: boolean;
  truncated: boolean;
  created_at: string;
  byte_count: number;
  character_count: number;
};

export type CommandLogPage = {
  execution_id: string;
  run_id: string;
  chunks: CommandLogChunk[];
  total: number;
  offset: number;
  limit: number;
};

export function listCommandTemplates(
  client: ApiClient = apiClient,
): Promise<CommandTemplateListDto> {
  return client.get<CommandTemplateListDto>("/api/v1/operator/command-templates");
}

export function getCommandTemplate(
  templateId: string,
  client: ApiClient = apiClient,
): Promise<CommandTemplateDto> {
  return client.get<CommandTemplateDto>(
    `/api/v1/operator/command-templates/${encodeURIComponent(templateId)}`,
  );
}

export function validateCommandPolicy(
  request: CommandPolicyValidateRequestDto,
  client: ApiClient = apiClient,
): Promise<CommandPolicyValidateResponseDto> {
  return client.post<CommandPolicyValidateResponseDto>(
    "/api/v1/operator/command-policy/validate",
    request,
  );
}

export function executeApprovedCommand(
  runId: string,
  request: CommandExecuteRequestDto,
  client: ApiClient = apiClient,
): Promise<CommandExecutionResponseDto> {
  return client.post<CommandExecutionResponseDto>(
    `/api/v1/runs/${encodeURIComponent(runId)}/commands`,
    request,
  );
}

export function listCommandExecutions(
  runId: string,
  client: ApiClient = apiClient,
): Promise<CommandExecutionListDto> {
  return client.get<CommandExecutionListDto>(
    `/api/v1/runs/${encodeURIComponent(runId)}/commands`,
  );
}

export function getCommandExecution(
  runId: string,
  executionId: string,
  client: ApiClient = apiClient,
): Promise<CommandExecutionResponseDto> {
  return client.get<CommandExecutionResponseDto>(
    `/api/v1/runs/${encodeURIComponent(runId)}/commands/${encodeURIComponent(executionId)}`,
  );
}

export type CancelCommandResponse = {
  execution_id: string;
  run_id: string;
  cancelled: boolean;
  signal_delivered: boolean;
  cancel_requested_at: string;
  idempotent_replay: boolean;
};

export function cancelCommand(
  runId: string,
  executionId: string,
  request: { idempotency_key: string; actor: string },
  client: ApiClient = apiClient,
): Promise<CancelCommandResponse> {
  return client.post<CancelCommandResponse>(
    `/api/v1/runs/${encodeURIComponent(runId)}/commands/${encodeURIComponent(executionId)}/cancel`,
    request,
  );
}

export function getCommandArtifactById(
  artifactId: string,
  client: ApiClient = apiClient,
): Promise<CommandArtifactMetadata> {
  return client.get<CommandArtifactMetadata>(
    `/api/v1/artifacts/${encodeURIComponent(artifactId)}`,
  );
}

export function getCommandLogSummary(
  runId: string,
  executionId: string,
  client: ApiClient = apiClient,
): Promise<CommandLogSummary> {
  return client.get<CommandLogSummary>(
    `/api/v1/runs/${encodeURIComponent(runId)}/commands/${encodeURIComponent(executionId)}/logs/summary`,
  );
}

export function getCommandLogs(
  runId: string,
  executionId: string,
  params: { offset?: number; limit?: number; stream?: "stdout" | "stderr" | "system"; cursor?: number } = {},
  client: ApiClient = apiClient,
): Promise<CommandLogPage> {
  const query = new URLSearchParams();
  if (params.offset !== undefined) query.set("offset", String(params.offset));
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.stream !== undefined) query.set("stream", params.stream);
  if (params.cursor !== undefined) query.set("cursor", String(params.cursor));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return client.get<CommandLogPage>(
    `/api/v1/runs/${encodeURIComponent(runId)}/commands/${encodeURIComponent(executionId)}/logs${suffix}`,
  );
}
