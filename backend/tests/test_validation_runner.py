from pathlib import Path

import pytest

from app.services.validation_runner import (
    BuildAgent,
    TestAgent as TransformerTestAgent,
    ValidationRunner,
    ValidationRunnerError,
)


class SpyRunner:
    def __init__(self):
        self.calls = []

    def advance_group(self, session, continuation, group, **kwargs):
        self.calls.append((session, continuation, group, kwargs))
        return "queued"


def test_build_and_test_agents_delegate_to_the_same_runner():
    runner = SpyRunner()

    BuildAgent(runner).advance("db", "continuation", next_node="test")
    TransformerTestAgent(runner).advance(
        "db", "continuation", "tests", next_node="aggregate_validation"
    )

    assert [call[2] for call in runner.calls] == ["builds", "tests"]


def test_required_checks_are_exact_and_reject_unknown_checks():
    assert ValidationRunner.required_groups({"required_checks": ["test"]}) == ["tests"]
    with pytest.raises(ValidationRunnerError, match="Unsupported"):
        ValidationRunner.required_groups({"required_checks": ["invented-lint"]})


def test_required_groups_resolve_through_the_shared_registry():
    from app.domain.planning import VALIDATION_TARGET_GROUPS
    import app.services.validation_runner as module

    assert module.VALIDATION_TARGET_GROUPS is VALIDATION_TARGET_GROUPS
    assert ValidationRunner.required_groups(
        {"required_checks": ["build", "test", "lint"]}
    ) == ["builds", "tests", "lint"]


def test_source_fingerprint_ignores_generated_output(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.ts").write_text("one", encoding="utf-8")
    before = ValidationRunner.source_fingerprint(tmp_path)
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "bundle.js").write_text("generated", encoding="utf-8")

    assert ValidationRunner.source_fingerprint(tmp_path) == before
