"""Tests for the G01 command registry and policy engine services (S3-F01).

Covers:
- CommandRegistryService list/get/seed operations
- CommandPolicyEngineService validation checks
- Various accept/reject scenarios
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.domain.command import (
    AuthorizationDecision,
    CancellationPolicy,
    CommandTemplate,
    CommandTemplateStatus,
    DEFAULT_COMMAND_TEMPLATES,
    NetworkProfile,
)
from app.domain.contracts import CommandPolicyValidateRequestDto
from app.repositories.models.base import Base
from app.repositories.models.workflow import CommandTemplateModel, CommandAuthorizationAuditModel
from app.services.command_registry_service import (
    CommandPolicyEngineService,
    CommandRegistryService,
)


@pytest.fixture
def db_session(tmp_path: Path) -> Session:
    """Create an isolated SQLite in-memory database for each test."""
    engine = create_engine("sqlite://", echo=False)
    Base.metadata.create_all(engine)
    _session = sessionmaker(bind=engine)()
    yield _session
    _session.close()


@pytest.fixture
def registry() -> CommandRegistryService:
    return CommandRegistryService()


@pytest.fixture
def policy_engine() -> CommandPolicyEngineService:
    return CommandPolicyEngineService(require_plan_membership=False)


@pytest.fixture
def seeded_registry(registry: CommandRegistryService, db_session: Session) -> CommandRegistryService:
    """Pre-seed the registry with default templates."""
    registry.seed_defaults(db_session)
    return registry


class TestCommandRegistryService:
    """Tests for the structured command template registry."""

    def test_list_templates_returns_defaults_when_empty(self, registry: CommandRegistryService, db_session: Session):
        """When DB is empty, list_templates returns the default template list."""
        result = registry.list_templates(db_session)
        assert result.total == 6
        assert len(result.templates) == 6
        command_ids = {t.command_id for t in result.templates}
        assert "python-version" in command_ids
        assert "npm-ci-bootstrap" in command_ids

    def test_seed_defaults_creates_all_templates(self, registry: CommandRegistryService, db_session: Session):
        """Seeding populates the database with all default templates."""
        seeded = registry.seed_defaults(db_session)
        assert len(seeded) == 6
        rows = db_session.query(CommandTemplateModel).all()
        assert len(rows) == 6

    def test_seed_defaults_is_idempotent(self, registry: CommandRegistryService, db_session: Session):
        """Seeding twice does not create duplicate entries."""
        registry.seed_defaults(db_session)
        registry.seed_defaults(db_session)
        rows = db_session.query(CommandTemplateModel).all()
        assert len(rows) == 6

    def test_get_template_by_id(self, seeded_registry: CommandRegistryService, db_session: Session):
        """Can retrieve a specific template by its ID."""
        template = seeded_registry.get_template(db_session, "tpl-python-version")
        assert template is not None
        assert template.command_id == "python-version"
        assert template.executable == "python"
        assert template.arguments == ["--version"]

    def test_get_template_not_found(self, registry: CommandRegistryService, db_session: Session):
        """Non-existent template ID returns None."""
        template = registry.get_template(db_session, "non-existent")
        assert template is None

    def test_find_template_by_command_id(self, seeded_registry: CommandRegistryService, db_session: Session):
        """Can find a template by its logical command_id."""
        template = seeded_registry.find_template_by_command_id(db_session, "npm-ci-bootstrap")
        assert template is not None
        assert template.template_id == "tpl-npm-ci"
        assert template.max_output_bytes == 5_000_000

    def test_template_has_correct_defaults(self, registry: CommandRegistryService, db_session: Session):
        """Default templates have correct structure and values."""
        tpl = DEFAULT_COMMAND_TEMPLATES[0]
        assert tpl.template_id == "tpl-python-version"
        assert tpl.status == CommandTemplateStatus.ACTIVE
        assert tpl.version == 1

    def test_npm_ci_template_allows_env_vars(self):
        """The npm-ci template allows NODE_OPTIONS and NPM_CONFIG_CACHE."""
        tpl = [t for t in DEFAULT_COMMAND_TEMPLATES if t.command_id == "npm-ci-bootstrap"][0]
        assert "NODE_OPTIONS" in tpl.allowed_env_vars
        assert "NPM_CONFIG_CACHE" in tpl.allowed_env_vars

    def test_registry_has_windows_executable_aliases(self):
        """Templates include Windows exe aliases for cross-platform support."""
        tpl = [t for t in DEFAULT_COMMAND_TEMPLATES if t.command_id == "git-version"][0]
        assert "git.exe" in tpl.executable_aliases

    def test_allowed_executables_includes_primary_and_aliases(self):
        """allowed_executables property returns the full set."""
        tpl = [t for t in DEFAULT_COMMAND_TEMPLATES if t.command_id == "python-version"][0]
        allowed = tpl.allowed_executables
        assert "python" in allowed
        assert "python.exe" in allowed
        assert "py" in allowed


class TestCommandPolicyEngineService:
    """Tests for the command policy engine authorization checks."""

    def _validate_request(
        self,
        command_id: str = "python-version",
        executable: str = "python",
        arguments: list[str] | None = None,
        **overrides,
    ) -> CommandPolicyValidateRequestDto:
        args = arguments or ["--version"]
        return CommandPolicyValidateRequestDto(
            run_id=f"run-{uuid4().hex[:8]}",
            command_id=command_id,
            executable=executable,
            arguments=args,
            idempotency_key=f"test-{uuid4().hex[:8]}",
            **overrides,
        )

    def test_accepts_known_command_with_matching_args(
        self, policy_engine: CommandPolicyEngineService, db_session: Session, seeded_registry
    ):
        """A well-formed command request should be accepted."""
        request = self._validate_request()
        result = policy_engine.validate(db_session, request)
        assert result.decision == "accepted"
        assert len(result.reasons) == 0

    def test_rejects_unknown_command_id(
        self, policy_engine: CommandPolicyEngineService, db_session: Session
    ):
        """An unregistered command_id should be rejected."""
        request = self._validate_request(command_id="unknown-command")
        result = policy_engine.validate(db_session, request)
        assert result.decision == "rejected"
        assert any("not registered" in r for r in result.reasons)

    def test_rejects_wrong_executable(
        self, policy_engine: CommandPolicyEngineService, db_session: Session, seeded_registry
    ):
        """Using an executable that doesn't match the template should be rejected."""
        request = self._validate_request(executable="java")
        result = policy_engine.validate(db_session, request)
        assert result.decision == "rejected"
        assert any("mismatch" in r for r in result.reasons)

    def test_rejects_wrong_arguments(
        self, policy_engine: CommandPolicyEngineService, db_session: Session, seeded_registry
    ):
        """Arguments that don't match the template should be rejected."""
        request = self._validate_request(arguments=["--help"])
        result = policy_engine.validate(db_session, request)
        assert result.decision == "rejected"
        assert any("mismatch" in r for r in result.reasons)

    def test_rejects_unsupported_network_profile(
        self, policy_engine: CommandPolicyEngineService, db_session: Session, seeded_registry
    ):
        """An unsupported network profile should be rejected."""
        request = self._validate_request(network_profile="full-internet")
        result = policy_engine.validate(db_session, request)
        assert result.decision == "rejected"
        assert any("network" in r.lower() for r in result.reasons)

    def test_rejects_unsupported_cancellation_policy(
        self, policy_engine: CommandPolicyEngineService, db_session: Session, seeded_registry
    ):
        """An unsupported cancellation policy should be rejected."""
        request = self._validate_request(cancellation_policy="invalid_policy")
        result = policy_engine.validate(db_session, request)
        assert result.decision == "rejected"
        assert any("cancellation" in r.lower() for r in result.reasons)

    def test_rejects_zero_timeout(
        self, policy_engine: CommandPolicyEngineService, db_session: Session, seeded_registry
    ):
        """A timeout of zero should be rejected by the policy engine."""
        # DTO enforces gt=0, so test through the domain validation directly
        check = policy_engine._check_timeout(0)
        assert not check.passed
        assert "timeout" in check.reason.lower()

    def test_rejects_timeout_over_max(
        self, policy_engine: CommandPolicyEngineService, db_session: Session, seeded_registry
    ):
        """A timeout over the maximum should be rejected by the policy engine."""
        check = policy_engine._check_timeout(7200)
        assert not check.passed
        assert "timeout" in check.reason.lower()

    def test_authorization_has_correct_output_structure(
        self, policy_engine: CommandPolicyEngineService, db_session: Session, seeded_registry
    ):
        """The authorization response has the correct schema."""
        request = self._validate_request()
        result = policy_engine.validate(db_session, request)
        assert len(result.authorization_id) > 0
        assert result.run_id == request.run_id
        assert result.command_id == request.command_id
        assert result.executable == request.executable
        assert result.arguments == request.arguments

    def test_windows_executable_alias_is_accepted(
        self, policy_engine: CommandPolicyEngineService, db_session: Session, seeded_registry
    ):
        """Windows executable aliases (e.g., python.exe) should be accepted."""
        request = self._validate_request(executable="python.exe")
        result = policy_engine.validate(db_session, request)
        assert result.decision == "accepted"

    def test_npm_ci_command_accepts_bootstrap(
        self, policy_engine: CommandPolicyEngineService, db_session: Session, seeded_registry
    ):
        """The npm-ci bootstrap command should be accepted with 'ci' arguments."""
        request = self._validate_request(
            command_id="npm-ci-bootstrap",
            executable="npm",
            arguments=["ci"],
        )
        result = policy_engine.validate(db_session, request)
        assert result.decision == "accepted"

    def test_accepts_windows_npm_alias(
        self, policy_engine: CommandPolicyEngineService, db_session: Session, seeded_registry
    ):
        """The npm.cmd alias should be accepted."""
        request = self._validate_request(
            command_id="npm-ci-bootstrap",
            executable="npm.cmd",
            arguments=["ci"],
        )
        result = policy_engine.validate(db_session, request)
        assert result.decision == "accepted"
