import type { MigrationRunDto } from "@/types/generated/api";

/** Test fixture matching the backend /migrations/mock-state response. */
export const mockMigrationRun: MigrationRunDto = {
  run_id: "mock-run-angular-18-to-21",
  status: "WAITING_PLAN_APPROVAL",
  source_angular_version: "18.x",
  target_angular_version: "21.x",
  created_at: "2026-07-10T00:00:00Z",
  updated_at: "2026-07-10T00:00:00Z",
  stages: [
    { stage_id: "angular-18-to-19", run_id: "mock-run-angular-18-to-21", stage_order: 1, source_angular_version: "18.x", target_angular_version: "19.x", status: "STAGE_CREATED", current_agent: null, created_at: "2026-07-10T00:00:00Z", started_at: null, completed_at: null },
    { stage_id: "angular-19-to-20", run_id: "mock-run-angular-18-to-21", stage_order: 2, source_angular_version: "19.x", target_angular_version: "20.x", status: "STAGE_CREATED", current_agent: null, created_at: "2026-07-10T00:00:00Z", started_at: null, completed_at: null },
    { stage_id: "angular-20-to-21", run_id: "mock-run-angular-18-to-21", stage_order: 3, source_angular_version: "20.x", target_angular_version: "21.x", status: "STAGE_CREATED", current_agent: null, created_at: "2026-07-10T00:00:00Z", started_at: null, completed_at: null }
  ],
  agent_executions: [
    { execution_id: "agent-execution-planning", run_id: "mock-run-angular-18-to-21", stage_id: null, agent_name: "Planning Agent", status: "COMPLETED", started_at: "2026-07-10T00:00:00Z", finished_at: "2026-07-10T00:00:00Z", summary: "Mock plan prepared for approval." }
  ],
  validation_gates: [
    { gate_id: "gate-browser-smoke", run_id: "mock-run-angular-18-to-21", stage_id: "angular-18-to-19", name: "browser_smoke", status: "manual_validation_required", checked_at: "2026-07-10T00:00:00Z", details: "Manual validation is required in Sprint 0." }
  ],
  approval_events: [
    { approval_id: "approval-plan", run_id: "mock-run-angular-18-to-21", stage_id: null, decision: "PENDING", requested_at: "2026-07-10T00:00:00Z", decided_at: null, actor: null, rationale: "Mock plan approval is pending." }
  ],
  artifacts: [
    { artifact_id: "artifact-mock-plan", run_id: "mock-run-angular-18-to-21", stage_id: "angular-18-to-19", artifact_type: "markdown", relative_path: "03_planning/mock_migration_plan.md", created_at: "2026-07-10T00:00:00Z", checksum: "mock-checksum-plan" }
  ],
  command_requests: [
    { command_id: "command-stage-19", run_id: "mock-run-angular-18-to-21", stage_id: "angular-18-to-19", requester: "Transformation Agent", executable: "npx", arguments: ["ng", "update", "@angular/core@19"], working_directory: "sandbox://mock-run-angular-18-to-21", requested_at: "2026-07-10T00:00:00Z" }
  ],
  command_results: [
    { command_id: "command-stage-19", run_id: "mock-run-angular-18-to-21", stage_id: "angular-18-to-19", status: "PENDING", started_at: "2026-07-10T00:00:00Z", finished_at: null, duration_ms: null, exit_code: null, stdout_artifact: null, stderr_artifact: null }
  ],
  patch_ledger: [
    { patch_id: "patch-placeholder", run_id: "mock-run-angular-18-to-21", stage_id: "angular-18-to-19", affected_files: ["src/app/app.config.ts"], change_summary: "Mock placeholder only; no patch was applied.", risk_level: "low", created_at: "2026-07-10T00:00:00Z", validation_status: "skipped_not_applicable" }
  ],
  repair_attempts: [
    { repair_attempt_id: "repair-placeholder", run_id: "mock-run-angular-18-to-21", stage_id: "angular-18-to-19", attempt_number: 1, status: "SKIPPED", risk_level: "low", created_at: "2026-07-10T00:00:00Z", diagnosis: "No repair is required for mock state." }
  ],
  workflow_events: [
    { event_id: "event-approval-required", run_id: "mock-run-angular-18-to-21", stage_id: null, event_type: "approval_required", occurred_at: "2026-07-10T00:00:00Z", payload: { approval_id: "approval-plan", status: "WAITING_PLAN_APPROVAL" } }
  ]
};
