"""Mock agent implementations for Sprint 0.

Every mock agent inherits ``BaseMockAgent`` and returns a deterministic
``AgentOutputEnvelope`` without LLM reasoning, file mutation, or command
execution. The orchestrator calls these agents through the shared contract
so future real agents can replace mock logic incrementally.

Agent catalog:
  AI Assistant Agent — explains workflow state; no execution or mutation.
  Eligibility and Constraint Agent — confirms Angular 11+; read-only.
  Analysis Agent — inventories workspace; read-only.
  Planning Agent — generates upgrade ladder; no mutation.
  Transformation Agent — mock upgrade commands; sandbox only.
  Build / Validation Agent — mock build validation; no repair.
  Repair Agent — mock low-risk repair; max three attempts.
  Report Agent — evidence report from persisted artifacts.
"""

from app.agents.base import BaseMockAgent
from app.domain.contracts import (
    AgentInputEnvelope,
    AgentOutputEnvelope,
    AgentStatus,
    RiskEntry,
    RiskLevel,
    RunStatus,
)


class AIAssistantAgent(BaseMockAgent):
    @property
    def name(self) -> str:
        return "AI Assistant Agent"

    def execute(self, envelope: AgentInputEnvelope) -> AgentOutputEnvelope:
        return AgentOutputEnvelope(
            agent_name=self.name,
            run_id=envelope.run_id,
            stage_id=envelope.stage_id,
            status=AgentStatus.COMPLETED,
            summary="Mock assistant ready to explain workflow state and route approval decisions through the backend.",
            artifacts_created=[],
            risks=[],
            requires_human_action=False,
            next_recommended_state=envelope.current_workflow_state,
        )


class EligibilityAgent(BaseMockAgent):
    @property
    def name(self) -> str:
        return "Eligibility and Constraint Agent"

    def execute(self, envelope: AgentInputEnvelope) -> AgentOutputEnvelope:
        return AgentOutputEnvelope(
            agent_name=self.name,
            run_id=envelope.run_id,
            stage_id=envelope.stage_id,
            status=AgentStatus.COMPLETED,
            summary="Mock eligibility check accepted Angular 18.x as Angular 11+ compatible.",
            artifacts_created=[
                "00_job_setup/eligibility_result.json",
                "00_job_setup/client_constraints.json",
            ],
            risks=[],
            requires_human_action=False,
            next_recommended_state=RunStatus.RUNNING,
        )


class AnalysisAgent(BaseMockAgent):
    @property
    def name(self) -> str:
        return "Analysis Agent"

    def execute(self, envelope: AgentInputEnvelope) -> AgentOutputEnvelope:
        return AgentOutputEnvelope(
            agent_name=self.name,
            run_id=envelope.run_id,
            stage_id=envelope.stage_id,
            status=AgentStatus.COMPLETED,
            summary="Mock analysis inventoried Angular workspace, dependencies, routes, and backend integration points.",
            artifacts_created=[
                "02_analysis/angular_workspace_analysis.json",
                "02_analysis/package_inventory.json",
                "02_analysis/route_inventory.json",
            ],
            risks=[
                RiskEntry(
                    risk_id="dependency-peer-conflict-risk",
                    severity=RiskLevel.MEDIUM,
                    description="Some packages may require version alignment during Angular 19 stage.",
                ),
            ],
            requires_human_action=False,
            next_recommended_state=RunStatus.WAITING,
        )


class PlanningAgent(BaseMockAgent):
    @property
    def name(self) -> str:
        return "Planning Agent"

    def execute(self, envelope: AgentInputEnvelope) -> AgentOutputEnvelope:
        return AgentOutputEnvelope(
            agent_name=self.name,
            run_id=envelope.run_id,
            stage_id=envelope.stage_id,
            status=AgentStatus.COMPLETED,
            summary="Mock plan generated upgrade ladder 18→19→20→21 with stage toolchain profiles and validation gates.",
            artifacts_created=[
                "03_planning/migration_plan.yaml",
                "03_planning/upgrade_ladder.yaml",
                "03_planning/stage_toolchain_profiles.json",
            ],
            risks=[],
            requires_human_action=False,
            next_recommended_state=RunStatus.WAITING,
        )


class TransformationAgent(BaseMockAgent):
    @property
    def name(self) -> str:
        return "Transformation Agent"

    def execute(self, envelope: AgentInputEnvelope) -> AgentOutputEnvelope:
        stage = envelope.stage_id or "unknown-stage"
        return AgentOutputEnvelope(
            agent_name=self.name,
            run_id=envelope.run_id,
            stage_id=envelope.stage_id,
            status=AgentStatus.COMPLETED,
            summary=f"Mock transformation applied approved Angular upgrade for {stage}.",
            artifacts_created=[
                f"05_sandbox_transform/{stage}_patch_ledger.json",
                f"05_sandbox_transform/{stage}_diff.patch",
            ],
            risks=[],
            requires_human_action=False,
            next_recommended_state=RunStatus.RUNNING,
        )


class BuildValidationAgent(BaseMockAgent):
    @property
    def name(self) -> str:
        return "Build / Validation Agent"

    def execute(self, envelope: AgentInputEnvelope) -> AgentOutputEnvelope:
        stage = envelope.stage_id or "unknown-stage"
        return AgentOutputEnvelope(
            agent_name=self.name,
            run_id=envelope.run_id,
            stage_id=envelope.stage_id,
            status=AgentStatus.COMPLETED,
            summary=f"Mock build validation passed for {stage}: install, build, and route inventory checked.",
            artifacts_created=[
                f"06_validation/{stage}_build_report.json",
                f"06_validation/{stage}_route_inventory.json",
            ],
            risks=[
                RiskEntry(
                    risk_id="manual-browser-smoke-required",
                    severity=RiskLevel.LOW,
                    description="Browser smoke test is manual in MVP and must be verified outside the platform.",
                ),
            ],
            requires_human_action=False,
            next_recommended_state=RunStatus.RUNNING,
        )


class RepairAgent(BaseMockAgent):
    @property
    def name(self) -> str:
        return "Repair Agent"

    def execute(self, envelope: AgentInputEnvelope) -> AgentOutputEnvelope:
        stage = envelope.stage_id or "unknown-stage"
        return AgentOutputEnvelope(
            agent_name=self.name,
            run_id=envelope.run_id,
            stage_id=envelope.stage_id,
            status=AgentStatus.SKIPPED,
            summary=f"Mock repair skipped for {stage}: no migration-caused errors detected.",
            artifacts_created=[
                f"07_repair/{stage}_repair_attempts.json",
            ],
            risks=[],
            requires_human_action=False,
            next_recommended_state=RunStatus.RUNNING,
        )


class ReportAgent(BaseMockAgent):
    @property
    def name(self) -> str:
        return "Report Agent"

    def execute(self, envelope: AgentInputEnvelope) -> AgentOutputEnvelope:
        return AgentOutputEnvelope(
            agent_name=self.name,
            run_id=envelope.run_id,
            stage_id=envelope.stage_id,
            status=AgentStatus.COMPLETED,
            summary="Mock final evidence report generated from persisted artifacts.",
            artifacts_created=[
                "08_final/final_evidence_report.md",
                "08_final/manual_actions.md",
                "08_final/llm_usage_summary.md",
            ],
            risks=[],
            requires_human_action=False,
            next_recommended_state=RunStatus.COMPLETED,
        )


MOCK_AGENTS: list[BaseMockAgent] = [
    AIAssistantAgent(),
    EligibilityAgent(),
    AnalysisAgent(),
    PlanningAgent(),
    TransformationAgent(),
    BuildValidationAgent(),
    RepairAgent(),
    ReportAgent(),
]

MOCK_AGENT_NAMES = [agent.name for agent in MOCK_AGENTS]
