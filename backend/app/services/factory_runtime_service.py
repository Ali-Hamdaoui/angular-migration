"""Durable single-generation authority for Factory processes."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.database import active_revisions
from app.repositories.models import FactoryRuntimeModel


class StaleFactoryRuntimeError(RuntimeError):
    code = "STALE_FACTORY_RUNTIME"


class FactoryRuntimeService:
    def __init__(self) -> None:
        self.generation = os.environ.get("FACTORY_RUNTIME_GENERATION", "").strip()
        self.factory_git_sha = os.environ.get("FACTORY_GIT_SHA", "").strip()
        self.database_identity = os.environ.get("FACTORY_DATABASE_IDENTITY", "").strip()
        self.launcher_pid = int(os.environ.get("FACTORY_LAUNCHER_PID", "0"))
        if not all((self.generation, self.factory_git_sha, self.database_identity, self.launcher_pid)):
            raise StaleFactoryRuntimeError("Factory runtime environment is incomplete")

    @property
    def worker_identity(self) -> str:
        return f"{self.generation}:{self.factory_git_sha[:12]}"

    def activate(self, session, alembic_head: str) -> FactoryRuntimeModel:
        now = datetime.now(UTC)
        for runtime in session.scalars(select(FactoryRuntimeModel).where(
            FactoryRuntimeModel.database_identity == self.database_identity,
            FactoryRuntimeModel.status == "active",
        )):
            if runtime.id != self.generation:
                runtime.status = "retired"
                runtime.retired_at = now
        session.flush()
        model = session.get(FactoryRuntimeModel, self.generation)
        if model is None:
            model = FactoryRuntimeModel(
                id=self.generation, factory_git_sha=self.factory_git_sha,
                database_identity=self.database_identity, alembic_head=alembic_head,
                launcher_pid=self.launcher_pid, status="active", started_at=now,
            )
            session.add(model)
        elif (model.factory_git_sha, model.database_identity, model.launcher_pid) != (
            self.factory_git_sha, self.database_identity, self.launcher_pid
        ):
            raise StaleFactoryRuntimeError("Runtime generation identity was reused with different provenance")
        else:
            model.status = "active"
            model.retired_at = None
        session.flush()
        return model

    def assert_active(self, session) -> FactoryRuntimeModel:
        model = session.scalar(select(FactoryRuntimeModel).where(
            FactoryRuntimeModel.database_identity == self.database_identity,
            FactoryRuntimeModel.status == "active",
        ))
        if model is None or model.id != self.generation or model.factory_git_sha != self.factory_git_sha:
            raise StaleFactoryRuntimeError(
                f"STALE_FACTORY_RUNTIME: {self.worker_identity} is not active for this database"
            )
        return model

    def retire(self, session) -> None:
        model = session.get(FactoryRuntimeModel, self.generation)
        if model is not None and model.status == "active":
            model.status = "retired"
            model.retired_at = datetime.now(UTC)


def main() -> None:
    from app.repositories.session import engine, session_scope

    service = FactoryRuntimeService()
    action = os.environ.get("FACTORY_RUNTIME_ACTION", "activate")
    with session_scope() as session:
        if action == "retire":
            service.retire(session)
            result = {"status": "retired", "runtime_generation_id": service.generation}
        else:
            model = service.activate(session, ",".join(active_revisions(engine)))
            result = {
                "status": model.status, "runtime_generation_id": model.id,
                "factory_git_sha": model.factory_git_sha,
                "database_identity": model.database_identity,
                "alembic_head": model.alembic_head, "launcher_pid": model.launcher_pid,
            }
    print(json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
