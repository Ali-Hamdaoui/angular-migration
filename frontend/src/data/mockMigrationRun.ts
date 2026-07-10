import type { MigrationRun } from "@/types/migration";

/** Read-only fixture matching the backend /migrations/mock-state response. */
export const mockMigrationRun: MigrationRun = {
  run_id: "mock-run-angular-18-to-21",
  status: "WAITING_PLAN_APPROVAL",
  source_angular_version: "18.x",
  target_angular_version: "21.x",
  created_at: "2026-07-10T00:00:00Z",
  updated_at: "2026-07-10T00:00:00Z",
  stages: [
    { stage_id: "angular-18-to-19", stage_order: 1, source_angular_version: "18.x", target_angular_version: "19.x", status: "STAGE_CREATED" },
    { stage_id: "angular-19-to-20", stage_order: 2, source_angular_version: "19.x", target_angular_version: "20.x", status: "STAGE_CREATED" },
    { stage_id: "angular-20-to-21", stage_order: 3, source_angular_version: "20.x", target_angular_version: "21.x", status: "STAGE_CREATED" }
  ],
  agent_executions: [{ execution_id: "agent-execution-planning", agent_name: "Planning Agent", status: "COMPLETED", summary: "Mock plan prepared for approval." }],
  validation_gates: [{ gate_id: "gate-browser-smoke", name: "browser_smoke", status: "manual_validation_required", details: "Manual validation is required in Sprint 0." }],
  approval_events: [{ approval_id: "approval-plan", decision: "PENDING", rationale: "Mock plan approval is pending." }],
  artifacts: [{ artifact_id: "artifact-mock-plan", artifact_type: "markdown", relative_path: "03_planning/mock_migration_plan.md", checksum: "mock-checksum-plan" }],
  command_requests: [{ command_id: "command-stage-19", requester: "Transformation Agent", executable: "npx", arguments: ["ng", "update", "@angular/core@19"], working_directory: "sandbox://mock-run-angular-18-to-21" }],
  command_results: [{ command_id: "command-stage-19", status: "PENDING" }],
  patch_ledger: [{ patch_id: "patch-placeholder", affected_files: ["src/app/app.config.ts"], change_summary: "Mock placeholder only; no patch was applied.", risk_level: "low", validation_status: "skipped_not_applicable" }],
  repair_attempts: [{ repair_attempt_id: "repair-placeholder", attempt_number: 1, status: "SKIPPED", risk_level: "low", diagnosis: "No repair is required for mock state." }],
  workflow_events: [{ event_id: "event-approval-required", event_type: "approval_required" }]
};