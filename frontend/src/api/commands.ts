import { apiClient, type createApiClient } from "./client";
import type {
  CommandTemplateListDto,
  CommandTemplateDto,
  CommandPolicyValidateRequestDto,
  CommandPolicyValidateResponseDto,
  CommandExecuteRequestDto,
  CommandExecutionResponseDto,
  CommandExecutionListDto,
} from "@/types/generated/api";

type ApiClient = ReturnType<typeof createApiClient>;

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
