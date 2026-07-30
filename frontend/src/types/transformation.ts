export type TransformationProjection = {
  run_id: string;
  continuation_id: string;
  stage_id: string;
  status: string;
  current_node: string;
  state_version: number;
  stage_status: string;
  source_version: string | null;
  target_version: string | null;
  checkpoint_kind: string | null;
  workspace_fingerprint: string | null;
  active_gate: string | null;
  active_command_id: string | null;
  active_command_status: string | null;
  active_prompt_id: string | null;
  last_error_code: string | null;
  cancel_requested_at: string | null;
};
