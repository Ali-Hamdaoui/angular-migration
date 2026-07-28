"""G01 domain aggregates for governed command execution.

StructuredCommandRegistry and CommandPolicyEngine are the authoritative
pre-execution boundary. Every execution path must pass through these
domain rules before a process is started.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Final


class CommandTemplateStatus(str, Enum):
    """Lifecycle status for a registered command template."""
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


class AuthorizationDecision(str, Enum):
    """Result of a policy-engine authorization check."""
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class NetworkProfile(str, Enum):
    """Network access profiles for command execution."""
    NONE = "none"
    REGISTRY_ONLY = "registry_only"
    REGISTRY_NPM = "registry_npm"
    FULL = "full"


class CancellationPolicy(str, Enum):
    """How cancellation is applied to a running command."""
    TERMINATE_PROCESS_TREE = "terminate_process_tree"
    WAIT_FOR_SAFE_POINT = "wait_for_safe_point"


@dataclass(frozen=True)
class CommandTemplate:
    """One registered command shape in the structured registry.

    This is the authoritative representation of a safe, registered command.
    Every field is validated before the template is activated.
    """

    template_id: str
    command_id: str
    executable: str
    arguments: tuple[str, ...]
    executable_aliases: tuple[str, ...] = ()
    description: str = ""
    status: CommandTemplateStatus = CommandTemplateStatus.ACTIVE
    version: int = 1
    allowed_env_vars: tuple[str, ...] = ()
    max_output_bytes: int | None = 1_000_000
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def allowed_executables(self) -> frozenset[str]:
        return frozenset((self.executable, *self.executable_aliases))

    def validate_executable(self, executable: str) -> bool:
        return executable in self.allowed_executables

    def validate_arguments(self, arguments: tuple[str, ...]) -> bool:
        return arguments == self.arguments


@dataclass(frozen=True)
class CommandPolicyRule:
    """One policy rule that governs command execution.

    Rules are combined conjunctively — all applicable rules must permit
    execution for a command to be authorized.
    """

    rule_id: str
    name: str
    description: str = ""
    rule_type: str = "builtin"  # builtin, plan_check, env_check, network_check
    allow_shell: bool = False
    require_plan_membership: bool = True
    require_approved_stage_plan: bool = False
    allowed_network_profiles: frozenset[NetworkProfile] = field(
        default_factory=lambda: frozenset({NetworkProfile.NONE})
    )
    allowed_cancellation_policies: frozenset[CancellationPolicy] = field(
        default_factory=lambda: frozenset({CancellationPolicy.TERMINATE_PROCESS_TREE})
    )
    default_timeout_seconds: int = 300
    max_timeout_seconds: int = 3600
    version: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class AuthorizationCheckResult:
    """Result of a single policy-engine check."""

    passed: bool
    rule_name: str
    reason: str | None = None


@dataclass(frozen=True)
class AuthorizationRequest:
    """Input to the CommandPolicyEngine for a single authorization decision."""

    run_id: str
    stage_id: str | None
    plan_id: str | None
    command_id: str
    executable: str
    arguments: tuple[str, ...]
    cwd_alias: str | None
    working_directory: str | None
    execution_profile_id: str
    network_profile: NetworkProfile
    cancellation_policy: CancellationPolicy
    timeout_seconds: int
    idempotency_key: str
    requested_by: str
    requester: str


@dataclass(frozen=True)
class AuthorizationResult:
    """Complete authorization decision produced by the policy engine."""

    authorization_id: str
    run_id: str
    stage_id: str | None
    plan_id: str | None
    command_id: str
    executable: str
    arguments: tuple[str, ...]
    cwd_alias: str | None
    execution_profile_id: str
    decision: AuthorizationDecision
    reasons: tuple[str, ...] = ()
    policy_version: str = "s3-f01-v1"
    checks: tuple[AuthorizationCheckResult, ...] = ()
    idempotency_key: str | None = None
    created_at: datetime | None = None


# Default command templates for Sprint 3 pipeline
DEFAULT_COMMAND_TEMPLATES: Final[tuple[CommandTemplate, ...]] = (
    CommandTemplate(
        template_id="tpl-python-version",
        command_id="python-version",
        executable="python",
        arguments=("--version",),
        executable_aliases=("python.exe", "py", "py.exe"),
        description="Check Python runtime version",
    ),
    CommandTemplate(
        template_id="tpl-node-version",
        command_id="node-version",
        executable="node",
        arguments=("--version",),
        executable_aliases=("node.exe",),
        description="Check Node.js runtime version",
    ),
    CommandTemplate(
        template_id="tpl-npm-version",
        command_id="npm-version",
        executable="npm",
        arguments=("--version",),
        executable_aliases=("npm.cmd",),
        description="Check npm package manager version",
    ),
    CommandTemplate(
        template_id="tpl-npx-version",
        command_id="npx-version",
        executable="npx",
        arguments=("--version",),
        executable_aliases=("npx.cmd",),
        description="Check npx package runner version",
    ),
    CommandTemplate(
        template_id="tpl-git-version",
        command_id="git-version",
        executable="git",
        arguments=("--version",),
        executable_aliases=("git.exe",),
        description="Check Git version",
    ),
    CommandTemplate(
        template_id="tpl-npm-ci",
        command_id="npm-ci-bootstrap",
        executable="npm",
        arguments=("ci",),
        executable_aliases=("npm.cmd",),
        description="Clean install npm dependencies",
        allowed_env_vars=("NODE_OPTIONS", "NPM_CONFIG_CACHE"),
        max_output_bytes=5_000_000,
    ),
    CommandTemplate(
        template_id="tpl-npm-ci-final", command_id="npm-ci-final", executable="npm", arguments=("ci",),
        executable_aliases=("npm.cmd",), description="Final clean install after lockfile verification",
        allowed_env_vars=("NODE_OPTIONS", "NPM_CONFIG_CACHE"), max_output_bytes=5_000_000,
    ),
    CommandTemplate(
        template_id="tpl-angular-update-exact", command_id="angular-update-exact", executable="npx",
        arguments=(), executable_aliases=("npx.cmd",), description="Execute an approved exact Angular update",
        allowed_env_vars=("NODE_OPTIONS", "NPM_CONFIG_CACHE"), max_output_bytes=5_000_000,
    ),
    CommandTemplate(
        template_id="tpl-angular-version-verify", command_id="angular-version-verify", executable="npx",
        arguments=("ng", "version"), executable_aliases=("npx.cmd",), description="Verify Angular versions",
    ),
    CommandTemplate(
        template_id="tpl-npm-script-build-production", command_id="npm-script-build-production", executable="npm",
        arguments=(), executable_aliases=("npm.cmd",), description="Run a discovered production build target",
    ),
    CommandTemplate(
        template_id="tpl-npm-script-test-ci", command_id="npm-script-test-ci", executable="npm",
        arguments=(), executable_aliases=("npm.cmd",), description="Run a discovered test target",
    ),
    CommandTemplate(
        template_id="tpl-npm-script-lint", command_id="npm-script-lint", executable="npm",
        arguments=(), executable_aliases=("npm.cmd",), description="Run a discovered lint target",
    ),
)
