import { applyEventToRun } from "@/hooks/applyEventToRun";
import type { MigrationEventDto, MigrationRunDto } from "@/types/generated/api";
import { mockMigrationRun } from "@/data/mockMigrationRun";

function event(type: MigrationEventDto["event_type"], payload: Record<string, unknown>, id = "evt-test", stageId: string | null = "angular-18-to-19"): MigrationEventDto {
  return { event_id: id, run_id: "mock-run-angular-18-to-21", stage_id: stageId, event_type: type, occurred_at: "2026-07-10T12:00:00Z", sequence: 1, payload };
}

describe("applyEventToRun", () => {
  it("updates run status on run_state_changed", () => {
    const updated = applyEventToRun(mockMigrationRun, event("run_state_changed", { status: "RUNNING" }));
    expect(updated.status).toBe("RUNNING");
    expect(updated.updated_at).toBe("2026-07-10T12:00:00Z");
  });

  it("updates stage status on stage_state_changed", () => {
    const updated = applyEventToRun(mockMigrationRun, event("stage_state_changed", { status: "RUNNING" }));
    expect(updated.stages[0].status).toBe("RUNNING");
    expect(updated.stages[1].status).toBe("PENDING");
  });

  it("updates existing agent execution status", () => {
    const updated = applyEventToRun(
      mockMigrationRun,
      event("agent_state_changed", { execution_id: "agent-execution-planning", agent_name: "Planning Agent", status: "RUNNING" }),
    );
    expect(updated.agent_executions[0].status).toBe("RUNNING");
  });

  it("creates a new agent execution when it does not exist", () => {
    const updated = applyEventToRun(
      mockMigrationRun,
      event("agent_state_changed", { execution_id: "agent-execution-transform", agent_name: "Transformation Agent", status: "RUNNING" }, "evt-transform"),
    );
    expect(updated.agent_executions).toHaveLength(2);
    expect(updated.agent_executions[1].execution_id).toBe("agent-execution-transform");
    expect(updated.agent_executions[1].status).toBe("RUNNING");
  });

  it("updates existing component execution status", () => {
    const updated = applyEventToRun(
      mockMigrationRun,
      event("component_state_changed", { execution_id: "component-execution-topology", component_name: "Workspace Topology Classifier", component_type: "WorkspaceTopologyClassifier", status: "RUNNING" }, "evt-component", null),
    );
    expect(updated.component_executions[0].status).toBe("RUNNING");
  });

  it("creates a new component execution when it does not exist", () => {
    const updated = applyEventToRun(
      mockMigrationRun,
      event("component_state_changed", { execution_id: "component-execution-snapshot", component_name: "Snapshot Service", component_type: "SnapshotService", status: "PASSED" }, "evt-component-new", null),
    );
    expect(updated.component_executions).toHaveLength(2);
    expect(updated.component_executions[1].component_name).toBe("Snapshot Service");
  });
  it("updates existing validation gate status", () => {
    const updated = applyEventToRun(
      mockMigrationRun,
      event("validation_gate_changed", { gate_id: "gate-browser-smoke", name: "browser_smoke", status: "passed" }),
    );
    expect(updated.validation_gates[0].status).toBe("passed");
  });

  it("creates a new validation gate when it does not exist", () => {
    const updated = applyEventToRun(
      mockMigrationRun,
      event("validation_gate_changed", { gate_id: "gate-static-symbol", name: "static_symbol_check", status: "passed" }, "evt-gate-new"),
    );
    expect(updated.validation_gates).toHaveLength(2);
    expect(updated.validation_gates[1].gate_id).toBe("gate-static-symbol");
  });

  it("appends a new artifact on artifact_created", () => {
    const updated = applyEventToRun(
      mockMigrationRun,
      event("artifact_created", { artifact_id: "artifact-patch", artifact_type: "patch", relative_path: "05_sandbox_transform/patch.patch", checksum: "sha256:abc" }),
    );
    expect(updated.artifacts).toHaveLength(mockMigrationRun.artifacts.length + 1);
    expect(updated.artifacts.at(-1)?.artifact_id).toBe("artifact-patch");
    expect(updated.artifacts.at(-1)?.artifact_type).toBe("patch");
  });

  it("appends a new approval event on approval_required", () => {
    const updated = applyEventToRun(
      mockMigrationRun,
      event("approval_required", { approval_id: "approval-stage-2", decision: "PENDING", rationale: "Stage 2 approval required" }, "evt-approval", "angular-19-to-20"),
    );
    expect(updated.approval_events).toHaveLength(2);
    expect(updated.approval_events[1].approval_id).toBe("approval-stage-2");
  });

  it("updates run status on workflow_completed", () => {
    const updated = applyEventToRun(mockMigrationRun, event("workflow_completed", { status: "COMPLETED" }, "evt-complete", null));
    expect(updated.status).toBe("COMPLETED");
  });

  it("does not mutate the original run", () => {
    const original: MigrationRunDto = { ...mockMigrationRun };
    applyEventToRun(mockMigrationRun, event("run_state_changed", { status: "RUNNING" }));
    expect(mockMigrationRun).toEqual(original);
  });
});

describe("authoritative workflow dimensions", () => {
  it("projects contract migration dimensions from the backend event", () => {
    const updated = applyEventToRun(
      mockMigrationRun,
      event("STATE_CONTRACT_MIGRATED", {
        phase_status: "completed",
        approval_status: "approved",
        repair_status: "not_required",
      }),
    );
    expect(updated.phase_status).toBe("completed");
    expect(updated.approval_status).toBe("approved");
    expect(updated.repair_status).toBe("not_required");
  });
});
it("projects baseline events into the authoritative ordered workflow event list", () => {
  const baselineEvent = event("BASELINE_BUILD_STARTED", { kind: "build", next_state_version: 4 }, "evt-baseline", null);
  const updated = applyEventToRun(mockMigrationRun, baselineEvent);
  expect(updated.workflow_events.at(-1)?.event_type).toBe("BASELINE_BUILD_STARTED");
  expect(updated.workflow_events.at(-1)?.sequence).toBe(1);
  expect(applyEventToRun(updated, baselineEvent).workflow_events.filter((item) => item.event_id === "evt-baseline")).toHaveLength(1);
});