import { apiClient, type createApiClient } from "./client";
import type {
  CommandTemplateListDto,
  CommandTemplateDto,
  CommandPolicyValidateRequestDto,
  CommandPolicyValidateResponseDto,
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
