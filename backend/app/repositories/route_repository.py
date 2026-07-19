"""Repository for C-Lite failure route persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.domain.route import FailureRouteDecision
from app.repositories.models.workflow import FailureAttemptModel, FailureRouteModel


class RouteRepository:
    """Repository for FailureRouteModel and FailureAttemptModel."""

    # -- Route decisions -----------------------------------------------------------

    def save_route_decision(
        self,
        session: Session,
        run_id: str,
        failure_id: str,
        decision: FailureRouteDecision,
        idempotency_key: str,
        state_version: int,
    ) -> FailureRouteModel:
        """Persist a C-Lite route decision and return the ORM model."""
        now = datetime.now(UTC)
        model = FailureRouteModel(
            id=f"route-{uuid4().hex[:12]}",
            run_id=run_id,
            failure_id=failure_id,
            route=decision.route.value,
            policy_version=decision.policy_version,
            decision_checksum=decision.decision_checksum,
            actions=list(decision.actions),
            risk=decision.risk,
            state_version=state_version,
            idempotency_key=idempotency_key,
            created_at=now,
        )
        session.add(model)
        session.flush()
        return model

    def get_route_decision(
        self,
        session: Session,
        run_id: str,
        failure_id: str,
    ) -> FailureRouteModel | None:
        """Retrieve the route decision for a failure scoped to run."""
        return session.query(FailureRouteModel).filter(
            FailureRouteModel.run_id == run_id,
            FailureRouteModel.failure_id == failure_id,
        ).order_by(FailureRouteModel.created_at.desc()).first()

    # -- Retry attempts -----------------------------------------------------------

    def save_retry_attempt(
        self,
        session: Session,
        run_id: str,
        failure_id: str,
        attempt_number: int,
        route: str,
    ) -> FailureAttemptModel:
        """Persist a retry attempt record and return the ORM model."""
        now = datetime.now(UTC)
        model = FailureAttemptModel(
            id=f"attempt-{uuid4().hex[:12]}",
            run_id=run_id,
            failure_id=failure_id,
            attempt_number=attempt_number,
            route=route,
            retry_count=0,
            status="pending",
            max_retries=3,
            created_at=now,
        )
        session.add(model)
        session.flush()
        return model

    def get_attempts(
        self,
        session: Session,
        failure_id: str,
    ) -> list[FailureAttemptModel]:
        """Retrieve all retry attempts for a failure ordered by attempt number."""
        return session.query(FailureAttemptModel).filter(
            FailureAttemptModel.failure_id == failure_id,
        ).order_by(FailureAttemptModel.attempt_number.asc()).all()
