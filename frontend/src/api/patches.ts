/** G07 — Patch apply, repair validation, and repair chain API client. */

import { createApiClient, ApiClientError } from "./client";

const api = createApiClient();

/** S4-F07 — Apply a repair diff */
export interface PatchApplyRequest {
  proposal_id: string;
  diff_content: string;
  expected_checksum: string;
  expected_fingerprint: string;
  expected_state_version: number;
  expected_plan_version?: string;
  idempotency_key?: string;
  actor?: string;
  workspace_root?: string | null;
}

export interface PatchApplyResult {
  patch_apply_id: string;
  status: string;
  state_version: number;
  idempotent_replay: boolean;
  artifact_refs: Record<string, string>;
  failure_evidence: Record<string, unknown> | null;
}

export async function applyRepairDiff(
  runId: string,
  proposalId: string,
  request: PatchApplyRequest,
): Promise<PatchApplyResult> {
  return api.request<PatchApplyResult>(
    "POST",
    `/api/v1/runs/${runId}/repair-proposals/${proposalId}/apply`,
    request,
  );
}

export async function getApplyResult(
  runId: string,
  proposalId: string,
): Promise<PatchApplyResult> {
  return api.request<PatchApplyResult>(
    "GET",
    `/api/v1/runs/${runId}/repair-proposals/${proposalId}/apply-result`,
  );
}

/** S4-F08 — Validate repair */
export interface ValidateRepairRequest {
  attempt_id: string;
  preflight_id: string;
  diff_content: string;
  expected_profile_id: string;
  actual_profile_id: string;
  expected_plan_version?: string;
  actual_plan_version?: string;
  previous_errors?: string[];
  current_errors?: string[];
  artifact_set_checksum?: string;
  plan_version?: string;
  workspace_fingerprint?: string;
  idempotency_key?: string;
  actor?: string;
}

export interface ValidateRepairResult {
  attempt_id: string;
  preflight_status: string;
  validation_status: string;
  g11_gate_id: string;
  g11_status: string;
  state_version: number;
  artifact_refs: Record<string, string>;
  idempotent_replay: boolean;
}

export async function validateRepair(
  runId: string,
  attemptId: string,
  request: ValidateRepairRequest,
): Promise<ValidateRepairResult> {
  return api.request<ValidateRepairResult>(
    "POST",
    `/api/v1/runs/${runId}/repair-attempts/${attemptId}/validate`,
    request,
  );
}

export async function getValidationResult(
  runId: string,
  attemptId: string,
): Promise<ValidateRepairResult> {
  return api.request<ValidateRepairResult>(
    "GET",
    `/api/v1/runs/${runId}/repair-attempts/${attemptId}/validation`,
  );
}

/** G11 Gate decision */
export interface G11DecisionRequest {
  gate_id: string;
  decision: "APPROVED" | "REJECTED" | "MODIFICATION_REQUESTED";
  actor?: string;
  rationale?: string;
  current_state_version?: number;
  current_artifact_checksum?: string;
  current_workspace_fingerprint?: string;
  idempotency_key?: string;
}

export interface G11DecisionResult {
  gate_id: string;
  decision: string;
  status: string;
  stale_replay: boolean;
}

export async function decideG11(
  runId: string,
  request: G11DecisionRequest,
): Promise<G11DecisionResult> {
  return api.request<G11DecisionResult>(
    "POST",
    `/api/v1/runs/${runId}/approvals/G11/decisions`,
    request,
  );
}

/** S4-F09 — Repair chain */
export interface AttemptRecord {
  attempt_number: number;
  attempt_id: string;
  outcome: string;
}

export interface DiagnosticHold {
  reason: string;
  attempt_count: number;
  duplicate_count: number;
  held_at: string | null;
}

export interface RepairChainResult {
  chain_id: string;
  run_id: string;
  status: string;
  total_attempts: number;
  applied_attempts: number;
  duplicate_count: number;
  no_progress_reason: string | null;
  recovery_action: string | null;
  diagnostic_hold: DiagnosticHold | null;
  attempts: AttemptRecord[];
  state_version: number;
  artifact_refs: Record<string, string>;
}

export async function getRepairChain(
  runId: string,
  chainId: string,
): Promise<RepairChainResult> {
  return api.request<RepairChainResult>(
    "GET",
    `/api/v1/runs/${runId}/repair-chains/${chainId}`,
  );
}

export interface RecoverRepairRequest {
  chain_id: string;
  run_id: string;
  stage_id?: string;
  workspace_fingerprint_before?: string;
  source_input_fingerprint?: string;
  idempotency_key?: string;
  actor?: string;
}

export interface RecoverRepairResult {
  chain_id: string;
  action: string;
  status: string;
  state_version: number;
  artifact_refs: Record<string, string>;
  idempotent_replay: boolean;
}

export async function recoverRepairChain(
  runId: string,
  chainId: string,
  request: RecoverRepairRequest,
): Promise<RecoverRepairResult> {
  return api.request<RecoverRepairResult>(
    "POST",
    `/api/v1/runs/${runId}/repair-chains/${chainId}/recover`,
    request,
  );
}

export { ApiClientError };
