"""Detect, persist, and decide bounded Angular CLI prompts."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from app.domain.contracts import WorkflowEventType
from app.domain.transformation import PromptDecisionRequest
from app.repositories.models import (
    CommandExecutionModel,
    StageCheckpointModel,
    StagePromptRequestModel,
    TransformationContinuationModel,
)
from app.state import StateTransitionService


class TransformerPromptError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class DetectedPrompt:
    kind: str
    normalized: str
    options: tuple[dict[str, str], ...]
    checksum: str


class AngularPromptDetector:
    version = "angular-cli-prompt-v1"
    _patterns = (
        re.compile(r"(?is)(would you like[^\r\n?]{0,500}\?)"),
        re.compile(r"(?is)(do you want[^\r\n?]{0,500}\?)"),
        re.compile(r"(?im)^([^\r\n]{1,500}\[(?:y/n|Y/n|y/N)\][^\r\n]*)$"),
        re.compile(r"(?im)^([^\r\n]{1,500}\(y/n\)[^\r\n]*)$"),
    )

    def detect(self, text: str) -> DetectedPrompt | None:
        for pattern in self._patterns:
            match = pattern.search(text[-8192:])
            if match:
                normalized = " ".join(match.group(1).split())[:1000]
                checksum = "sha256:" + hashlib.sha256(normalized.encode()).hexdigest()
                return DetectedPrompt(
                    kind="boolean",
                    normalized=normalized,
                    options=(
                        {"option_id": "yes", "label": "Yes", "stdin": "y\n"},
                        {"option_id": "no", "label": "No", "stdin": "n\n"},
                    ),
                    checksum=checksum,
                )
        return None


class TransformerPromptService:
    def capture(
        self,
        session,
        execution: CommandExecutionModel,
        detected: DetectedPrompt,
        *,
        now: datetime | None = None,
    ) -> StagePromptRequestModel:
        existing = session.scalar(
            select(StagePromptRequestModel).where(
                StagePromptRequestModel.execution_id == execution.id,
                StagePromptRequestModel.prompt_checksum == detected.checksum,
            )
        )
        if existing is not None:
            return existing
        checkpoint = session.get(StageCheckpointModel, execution.checkpoint_id)
        if checkpoint is None:
            raise TransformerPromptError(
                "PROMPT_CHECKPOINT_MISSING",
                "Unexpected prompt cannot be governed without a pre-command checkpoint",
            )
        created_at = now or datetime.now(UTC)
        prompt = StagePromptRequestModel(
            id=f"prompt-{uuid4().hex[:12]}",
            run_id=execution.run_id,
            stage_id=execution.stage_id,
            execution_id=execution.id,
            kind=detected.kind,
            detector_version=AngularPromptDetector.version,
            normalized_prompt=detected.normalized,
            options_json=list(detected.options),
            context_artifact_ids=list(execution.artifact_ids or []),
            prompt_checksum=detected.checksum,
            pre_command_fingerprint=checkpoint.workspace_fingerprint,
            status="detected",
            reconstruction_checkpoint_id=checkpoint.id,
            created_at=created_at,
        )
        session.add(prompt)
        execution.prompt_request_id = prompt.id
        session.flush()
        StateTransitionService(session).append_audit_event(
            run_id=execution.run_id,
            idempotency_key=f"{execution.id}:{detected.checksum}:prompt",
            event_type=WorkflowEventType.CLI_PROMPT_CAPTURED,
            actor="transformer",
            reason="Angular CLI prompt detected; process-tree termination requested",
            occurred_at=created_at,
            payload={
                "stage_id": execution.stage_id,
                "execution_id": execution.id,
                "prompt_id": prompt.id,
                "prompt_checksum": detected.checksum,
            },
        )
        return prompt

    def decide(
        self,
        session,
        continuation: TransformationContinuationModel,
        prompt_id: str,
        request: PromptDecisionRequest,
        *,
        actor: str,
        now: datetime | None = None,
    ) -> StagePromptRequestModel:
        prompt = session.get(StagePromptRequestModel, prompt_id)
        if prompt is None or prompt.run_id != continuation.run_id:
            raise TransformerPromptError("PROMPT_NOT_FOUND", "Prompt request does not exist")
        checksum = self._checksum(
            {"prompt_id": prompt_id, "actor": actor, **request.model_dump(mode="json")}
        )
        if prompt.decision_idempotency_key is not None:
            if (
                prompt.decision_idempotency_key != request.idempotency_key
                or prompt.decision_request_checksum != checksum
            ):
                raise TransformerPromptError(
                    "IDEMPOTENCY_PAYLOAD_MISMATCH",
                    "Prompt decision key has a different payload",
                )
            return prompt
        if continuation.state_version != request.expected_state_version:
            raise TransformerPromptError("TRANSFORMATION_STATE_CONFLICT", "Transformer state changed; refresh")
        if prompt.status != "waiting_human" or prompt.prompt_checksum != request.prompt_checksum:
            raise TransformerPromptError("STALE_PROMPT_BINDING", "Prompt evidence is stale")
        option_ids = {item["option_id"] for item in prompt.options_json}
        if request.selected_option_id not in option_ids:
            raise TransformerPromptError("PROMPT_OPTION_INVALID", "Selected prompt option is not allowed")
        decided_at = now or datetime.now(UTC)
        prompt.status = "decided"
        prompt.selected_option_id = request.selected_option_id
        prompt.decision_actor = actor
        prompt.decision_idempotency_key = request.idempotency_key
        prompt.decision_request_checksum = checksum
        prompt.decided_at = decided_at
        continuation.status = "queued"
        continuation.current_node = "angular_update"
        continuation.worker_id = None
        continuation.lease_expires_at = None
        continuation.wake_sequence += 1
        continuation.state_version += 1
        continuation.updated_at = decided_at
        session.flush()
        StateTransitionService(session).append_audit_event(
            run_id=continuation.run_id,
            idempotency_key=f"{request.idempotency_key}:event",
            event_type=WorkflowEventType.CLI_PROMPT_DECIDED,
            actor=actor,
            reason="operator selected a bounded Angular CLI prompt option",
            occurred_at=decided_at,
            payload={
                "stage_id": continuation.current_stage_id,
                "prompt_id": prompt.id,
                "selected_option_id": prompt.selected_option_id,
            },
        )
        return prompt

    @staticmethod
    def selected_stdin(prompt: StagePromptRequestModel) -> str | None:
        selected = next(
            (
                item
                for item in prompt.options_json
                if item.get("option_id") == prompt.selected_option_id
            ),
            None,
        )
        return selected.get("stdin") if selected else None

    @staticmethod
    def _checksum(value: object) -> str:
        return "sha256:" + hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()
