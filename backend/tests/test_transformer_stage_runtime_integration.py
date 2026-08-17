from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.domain.runtime_execution import RuntimeExecutableKind
from app.repositories.models import MigrationStageModel
from app.services.command_executor_service import CommandExecutorError, _runtime_bindings_from_stage
from app.services.transformer_stage_service import TransformerStageError, TransformerStageService


NOW = datetime(2026, 8, 17, tzinfo=UTC)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _Session:
    def __init__(self, stage, rows):
        self.stage = stage
        self.rows = rows

    def get(self, model, identifier):
        return self.stage if model is MigrationStageModel and identifier == self.stage.id else None

    def scalars(self, _query):
        return _Result(self.rows)


class _StageRuntime:
    def __init__(self):
        self.calls = []

    def resolve_stage(self, stage_id, source_family, target_family):
        self.calls.append((stage_id, source_family, target_family))
        return SimpleNamespace(status="bound", blocked_reason=None)

    def record_binding(self, run_id, binding, *, actor):
        return []


def _rows(stage_id, runtime_id):
    return [
        SimpleNamespace(
            stage_id=stage_id,
            kind=kind.value,
            runtime_id=runtime_id,
            version_exact=version,
            sha256=("a" if kind is RuntimeExecutableKind.NODE else "b" if kind is RuntimeExecutableKind.NPM else "c") * 64,
            resolved_path=f"C:/runtimes/{runtime_id}/{kind.value}.exe",
            source="synthetic-stage-matrix",
            status="bound",
            created_at=NOW,
        )
        for kind, version in (
            (RuntimeExecutableKind.NODE, "12.22.12" if runtime_id == "node12" else "20.11.1"),
            (RuntimeExecutableKind.NPM, "8.19.4" if runtime_id == "node12" else "10.2.4"),
            (RuntimeExecutableKind.NPX, "8.19.4" if runtime_id == "node12" else "10.2.4"),
        )
    ]


def test_transformer_resolves_distinct_durable_runtime_bindings_per_stage():
    first_stage = SimpleNamespace(id="stage-11-12", source_version_family="angular-11.x", target_version_family="angular-12.x")
    second_stage = SimpleNamespace(id="stage-20-21", source_version_family="angular-20.x", target_version_family="angular-21.x")
    first_runtime = _StageRuntime()
    second_runtime = _StageRuntime()

    first = TransformerStageService(stage_runtime_service=first_runtime).resolve_stage_runtime(
        _Session(first_stage, _rows(first_stage.id, "node12")),
        SimpleNamespace(run_id="run-1", current_stage_id=first_stage.id),
    )
    second = TransformerStageService(stage_runtime_service=second_runtime).resolve_stage_runtime(
        _Session(second_stage, _rows(second_stage.id, "node20")),
        SimpleNamespace(run_id="run-1", current_stage_id=second_stage.id),
    )

    assert first["profile_id"] != second["profile_id"]
    assert first["node_executable"].endswith("node.exe")
    assert "node12" in first["node_executable"]
    assert "node20" in second["node_executable"]
    assert first_runtime.calls == [(first_stage.id, "angular-11.x", "angular-12.x")]
    assert second_runtime.calls == [(second_stage.id, "angular-20.x", "angular-21.x")]


def test_stage_runtime_binding_rejects_mixed_installations():
    stage = SimpleNamespace(id="stage-mixed", source_version_family="angular-11.x", target_version_family="angular-12.x")
    rows = _rows(stage.id, "node12")
    rows[-1].runtime_id = "node20"

    with pytest.raises(TransformerStageError, match="one installation"):
        TransformerStageService(stage_runtime_service=_StageRuntime()).resolve_stage_runtime(
            _Session(stage, rows),
            SimpleNamespace(run_id="run-1", current_stage_id=stage.id),
        )


def test_command_authority_reads_stage_runtime_rows():
    stage_id = "stage-command"
    bindings = _runtime_bindings_from_stage(_Session(SimpleNamespace(id=stage_id), _rows(stage_id, "node12")), stage_id)

    assert {item.runtime_id for item in bindings.values()} == {"node12"}
    assert bindings["node"].resolved_path.endswith("node.exe")
    assert bindings["npm"].version_exact == "8.19.4"


def test_command_authority_rejects_blocked_stage_runtime_rows():
    stage_id = "stage-blocked"
    rows = _rows(stage_id, "node12")
    rows[0].status = "blocked"

    with pytest.raises(CommandExecutorError, match="incomplete or blocked"):
        _runtime_bindings_from_stage(_Session(SimpleNamespace(id=stage_id), rows), stage_id)
