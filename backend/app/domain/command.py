"""G01 domain aggregates for governed command execution.

StructuredCommandRegistry and CommandPolicyEngine are the authoritative
pre-execution boundary. Every execution path must pass through these
domain rules before a process is started.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import re
from collections.abc import Mapping
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

    def matches_arguments(self, arguments: tuple[str, ...]) -> bool:
        """Match concrete arguments against literal tokens and named token fragments."""
        return command_arguments_match(self.arguments, arguments)


@dataclass(frozen=True)
class TransformationCommandDefinition:
    """One immutable command authority shared by planning and execution."""

    command_id: str
    template_id: str
    executable: str
    argument_patterns: tuple[str, ...]
    executable_aliases: tuple[str, ...] = ()
    timeout_seconds: int = 300
    network_profile: str = "approved-registries-only"
    conditional: bool = False
    allowed_env_vars: tuple[str, ...] = ()
    max_output_bytes: int | None = 1_000_000
    description: str = ""

    @property
    def arguments(self) -> tuple[str, ...]:
        return self.argument_patterns

    def render_arguments(self, bindings: Mapping[str, str] | None = None) -> tuple[str, ...]:
        values = dict(bindings or {})
        rendered: list[str] = []
        for pattern in self.argument_patterns:
            rendered.append(
                re.sub(
                    r"\{([a-z][a-z0-9_]*)\}",
                    lambda match: self._binding(match.group(1), values),
                    pattern,
                )
            )
        result = tuple(rendered)
        if not command_arguments_match(self.argument_patterns, result):
            raise ValueError(f"Invalid parameter binding for command {self.command_id}")
        return result

    @staticmethod
    def _binding(name: str, bindings: Mapping[str, str]) -> str:
        value = bindings.get(name)
        if not isinstance(value, str) or not value or any(
            character in value for character in "\r\n;|&<>`$()'\""
        ) or any(character.isspace() for character in value):
            raise ValueError(f"Invalid command parameter binding: {name}")
        return value

    def to_template(self) -> CommandTemplate:
        return CommandTemplate(
            template_id=self.template_id,
            command_id=self.command_id,
            executable=self.executable,
            arguments=self.argument_patterns,
            executable_aliases=self.executable_aliases,
            description=self.description,
            allowed_env_vars=self.allowed_env_vars,
            max_output_bytes=self.max_output_bytes,
        )


def command_arguments_match(patterns: tuple[str, ...], arguments: tuple[str, ...]) -> bool:
    if len(arguments) != len(patterns):
        return False
    for pattern, argument in zip(patterns, arguments, strict=True):
        expression = re.escape(pattern)
        expression = re.sub(r"\\\{[a-z][a-z0-9_]*\\\}", r"[^\\s;|&<>`$()]+", expression)
        if re.fullmatch(expression, argument) is None:
            return False
    return True


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
TRANSFORMATION_COMMAND_CATALOGUE: Final[dict[str, TransformationCommandDefinition]] = {
    "npm-ci-bootstrap": TransformationCommandDefinition(
        command_id="npm-ci-bootstrap", template_id="tpl-npm-ci", executable="npm", argument_patterns=("ci",),
        executable_aliases=("npm.cmd",), timeout_seconds=3600,
        allowed_env_vars=("NODE_OPTIONS", "NPM_CONFIG_CACHE"), max_output_bytes=5_000_000,
        description="Clean install npm dependencies",
    ),
    "angular-update-exact": TransformationCommandDefinition(
        command_id="angular-update-exact", template_id="tpl-angular-update-exact", executable="npx",
        argument_patterns=("--yes", "-p", "@angular/cli@{target_cli_exact}", "ng", "update", "@angular/core@{target_exact}", "@angular/cli@{target_cli_exact}", "--interactive=false"),
        executable_aliases=("npx.cmd",), timeout_seconds=1800,
        allowed_env_vars=("NODE_OPTIONS", "NPM_CONFIG_CACHE"), max_output_bytes=5_000_000,
        description="Execute an approved exact Angular update",
    ),
    "angular-version-verify": TransformationCommandDefinition(
        command_id="angular-version-verify", template_id="tpl-angular-version-verify", executable="npx",
        argument_patterns=("ng", "version"), executable_aliases=("npx.cmd",), timeout_seconds=300,
        description="Verify Angular versions",
    ),
    "npm-ci-final": TransformationCommandDefinition(
        command_id="npm-ci-final", template_id="tpl-npm-ci-final", executable="npm", argument_patterns=("ci",),
        executable_aliases=("npm.cmd",), timeout_seconds=3600,
        allowed_env_vars=("NODE_OPTIONS", "NPM_CONFIG_CACHE"), max_output_bytes=5_000_000,
        description="Final clean install after lockfile verification",
    ),
    "npm-script-build-production": TransformationCommandDefinition(
        command_id="npm-script-build-production", template_id="tpl-npm-script-build-production", executable="npm",
        argument_patterns=("run", "{build_script}", "--", "--configuration", "{build_configuration}"),
        executable_aliases=("npm.cmd",), timeout_seconds=3600,
        description="Run a discovered production build target",
    ),
    "npm-script-test-ci": TransformationCommandDefinition(
        command_id="npm-script-test-ci", template_id="tpl-npm-script-test-ci", executable="npm",
        argument_patterns=("run", "{test_script}", "--", "{test_watch_flag}"),
        executable_aliases=("npm.cmd",), timeout_seconds=3600,
        description="Run a discovered test target",
    ),
    "npm-script-lint": TransformationCommandDefinition(
        command_id="npm-script-lint", template_id="tpl-npm-script-lint", executable="npm",
        argument_patterns=("run", "{lint_script}"), executable_aliases=("npm.cmd",), timeout_seconds=1800,
        conditional=True, description="Run a discovered lint target",
    ),
}


_TRANSFORMATION_COMMAND_TEMPLATES: tuple[CommandTemplate, ...] = tuple(
    definition.to_template() for definition in TRANSFORMATION_COMMAND_CATALOGUE.values()
)


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
    *_TRANSFORMATION_COMMAND_TEMPLATES,
)
