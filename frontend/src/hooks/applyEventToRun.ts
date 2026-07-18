import type {
  AgentExecutionDto,
  AgentStatus,
  ArtifactRefDto,
  ArtifactType,
  ComponentExecutionDto,
  MigrationEventDto,
  MigrationRunDto,
  RunStatus,
  StageStatus,
  StepStatus,
  ValidationGateDto,
  ValidationStatus,
} from "@/types/generated/api";

/** Apply a backend SSE event to the current run state.
 *
 * The frontend never infers state; it maps event payloads to existing
 * DTO fields using the backend-owned vocabulary only.
 */
export function applyEventToRun(run: MigrationRunDto, event: MigrationEventDto): MigrationRunDto {
  const projected = applyEventToRunProjection(run, event);
  const workflow_events = [...projected.workflow_events.filter((item) => item.event_id !== event.event_id), event];
  return { ...projected, workflow_events };
}

function applyEventToRunProjection(run: MigrationRunDto, event: MigrationEventDto): MigrationRunDto {
  switch (event.event_type) {
    case "run_state_changed":
      return { ...run, status: event.payload.status as RunStatus, phase_status: (event.payload.phase_status as MigrationRunDto["phase_status"]) ?? run.phase_status, approval_status: (event.payload.approval_status as MigrationRunDto["approval_status"]) ?? run.approval_status, repair_status: (event.payload.repair_status as MigrationRunDto["repair_status"]) ?? run.repair_status, updated_at: event.occurred_at };

    case "stage_state_changed":
      return {
        ...run,
        stages: run.stages.map((stage) =>
          stage.stage_id === event.stage_id
            ? { ...stage, status: event.payload.status as StageStatus }
            : stage,
        ),
      };

    case "component_state_changed": {
      const executionId = event.payload.execution_id as string;
      const newStatus = event.payload.status as StepStatus;
      const exists = run.component_executions.some((c) => c.execution_id === executionId);
      const component_executions = exists
        ? run.component_executions.map((c) =>
            c.execution_id === executionId ? { ...c, status: newStatus } : c,
          )
        : [
            ...run.component_executions,
            {
              execution_id: executionId,
              run_id: run.run_id,
              stage_id: event.stage_id,
              component_name: event.payload.component_name as string,
              component_type: event.payload.component_type as ComponentExecutionDto["component_type"],
              status: newStatus,
              started_at: event.occurred_at,
              finished_at: null,
              summary: null,
            } satisfies ComponentExecutionDto,
          ];
      return { ...run, component_executions };
    }

    case "agent_state_changed": {
      const executionId = event.payload.execution_id as string;
      const newStatus = event.payload.status as AgentStatus;
      const exists = run.agent_executions.some((a) => a.execution_id === executionId);
      const agent_executions = exists
        ? run.agent_executions.map((a) =>
            a.execution_id === executionId ? { ...a, status: newStatus } : a,
          )
        : [
            ...run.agent_executions,
            {
              execution_id: executionId,
              run_id: run.run_id,
              stage_id: event.stage_id,
              agent_name: event.payload.agent_name as string,
              agent_kind: (event.payload.agent_kind as AgentExecutionDto["agent_kind"]) ?? null,
              status: newStatus,
              started_at: event.occurred_at,
              finished_at: null,
              summary: null,
            } satisfies AgentExecutionDto,
          ];
      return { ...run, agent_executions };
    }

    case "validation_gate_changed": {
      const gateId = event.payload.gate_id as string;
      const exists = run.validation_gates.some((g) => g.gate_id === gateId);
      const validation_gates = exists
        ? run.validation_gates.map((g) =>
            g.gate_id === gateId
              ? { ...g, status: event.payload.status as ValidationStatus, checked_at: event.occurred_at }
              : g,
          )
        : [
            ...run.validation_gates,
            {
              gate_id: gateId,
              run_id: run.run_id,
              stage_id: event.stage_id,
              name: event.payload.name as string,
              status: event.payload.status as ValidationStatus,
              checked_at: event.occurred_at,
              details: null,
            } satisfies ValidationGateDto,
          ];
      return { ...run, validation_gates };
    }

    case "artifact_created": {
      const newArtifact: ArtifactRefDto = {
        artifact_id: event.payload.artifact_id as string,
        run_id: run.run_id,
        stage_id: event.stage_id,
        artifact_type: event.payload.artifact_type as ArtifactType,
        relative_path: event.payload.relative_path as string,
        created_at: event.occurred_at,
        checksum: (event.payload.checksum as string | null) ?? "mock-event-checksum",
      };
      const exists = run.artifacts.some((a) => a.artifact_id === newArtifact.artifact_id);
      const artifacts = exists
        ? run.artifacts.map((a) => (a.artifact_id === newArtifact.artifact_id ? newArtifact : a))
        : [...run.artifacts, newArtifact];
      return { ...run, artifacts };
    }

    case "approval_required":
      return {
        ...run,
        approval_status: "pending",
        approval_events: [
          ...run.approval_events,
          {
            approval_id: event.payload.approval_id as string,
            run_id: run.run_id,
            stage_id: event.stage_id,
            decision: "PENDING",
            requested_at: event.occurred_at,
            decided_at: null,
            actor: null,
            rationale: (event.payload.rationale as string | null) ?? null,
          },
        ],
      };

    case "STATE_CONTRACT_MIGRATED":
      return { ...run, phase_status: (event.payload.phase_status as MigrationRunDto["phase_status"]) ?? run.phase_status, approval_status: (event.payload.approval_status as MigrationRunDto["approval_status"]) ?? run.approval_status, repair_status: (event.payload.repair_status as MigrationRunDto["repair_status"]) ?? run.repair_status, updated_at: event.occurred_at };

    case "workflow_completed":
      return { ...run, status: event.payload.status as RunStatus, phase_status: (event.payload.phase_status as MigrationRunDto["phase_status"]) ?? run.phase_status, approval_status: (event.payload.approval_status as MigrationRunDto["approval_status"]) ?? run.approval_status, repair_status: (event.payload.repair_status as MigrationRunDto["repair_status"]) ?? run.repair_status, updated_at: event.occurred_at };

    default:
      return run;
  }
}