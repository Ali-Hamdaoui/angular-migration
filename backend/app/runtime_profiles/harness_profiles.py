"""Harness subprocess profile definitions for Angular acceptance fixtures.

Extends the existing CommandRegistry with Angular CLI command definitions
that the AcceptanceHarnessService uses to execute fixture subprocesses.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.command_execution.worker import CancellationPolicy, CommandDefinition, CommandRegistry

HARNESS_PROFILE_ID = "harness-runtime-profile"

# Working directory aliases used by harness subprocess profiles.
HARNESS_FIXTURE_ROOT = "HARNESS_FIXTURE_ROOT"
HARNESS_OUTPUT_ROOT = "HARNESS_OUTPUT_ROOT"


def harness_default_timeout(executable: str) -> int:
    """Return a sensible default timeout for the given executable."""
    match executable:
        case "npm" | "npm.cmd":
            return 120
        case "npx" | "npx.cmd":
            return 120
        case "ng" | "ng.cmd":
            return 60
        case _:
            return 60


def build_harness_command_registry(
    *,
    extra_definitions: tuple[CommandDefinition, ...] | None = None,
) -> CommandRegistry:
    """Build a CommandRegistry extended with harness command definitions.

    The returned registry includes the standard Sprint 0 commands plus
    Angular CLI entries for fixture generation and evaluation.
    """
    base = CommandRegistry()  # includes python, node, npm, npx, git, npm-ci-bootstrap
    harness_commands: tuple[CommandDefinition, ...] = (
        CommandDefinition(
            command_id="ng-new",
            executable="ng",
            arguments=("new",),
            executable_aliases=("ng.cmd",),
        ),
        CommandDefinition(
            command_id="ng-generate",
            executable="ng",
            arguments=("generate",),
            executable_aliases=("ng.cmd",),
        ),
        CommandDefinition(
            command_id="ng-build",
            executable="ng",
            arguments=("build",),
            executable_aliases=("ng.cmd",),
        ),
        CommandDefinition(
            command_id="npm-install",
            executable="npm",
            arguments=("install",),
            executable_aliases=("npm.cmd",),
        ),
        CommandDefinition(
            command_id="npx-ng-update",
            executable="npx",
            arguments=("ng", "update"),
            executable_aliases=("npx.cmd",),
        ),
    )
    extra = extra_definitions or ()
    return CommandRegistry(
        definitions=base.definitions + harness_commands + extra
    )


# Convenience alias for unit tests and direct usage.
HARNESS_COMMAND_REGISTRY = build_harness_command_registry()


# Profile descriptor entries for the harness.
# Each maps a command_id to its harness-specific defaults.
HARNESS_PROFILE_ENTRIES: dict[str, dict] = {
    "ng-new": {
        "executable": "ng",
        "default_args": ("new",),
        "working_directory_alias": HARNESS_FIXTURE_ROOT,
        "timeout_seconds": 120,
        "network_profile": "none",
        "cancellation_policy": CancellationPolicy.TERMINATE_PROCESS_TREE,
    },
    "ng-generate": {
        "executable": "ng",
        "default_args": ("generate",),
        "working_directory_alias": HARNESS_FIXTURE_ROOT,
        "timeout_seconds": 60,
        "network_profile": "none",
        "cancellation_policy": CancellationPolicy.TERMINATE_PROCESS_TREE,
    },
    "ng-build": {
        "executable": "ng",
        "default_args": ("build",),
        "working_directory_alias": HARNESS_FIXTURE_ROOT,
        "timeout_seconds": 60,
        "network_profile": "none",
        "cancellation_policy": CancellationPolicy.TERMINATE_PROCESS_TREE,
    },
    "npm-install": {
        "executable": "npm",
        "default_args": ("install",),
        "working_directory_alias": HARNESS_FIXTURE_ROOT,
        "timeout_seconds": 120,
        "network_profile": "none",
        "cancellation_policy": CancellationPolicy.TERMINATE_PROCESS_TREE,
    },
    "npx-ng-update": {
        "executable": "npx",
        "default_args": ("ng", "update"),
        "working_directory_alias": HARNESS_FIXTURE_ROOT,
        "timeout_seconds": 120,
        "network_profile": "none",
        "cancellation_policy": CancellationPolicy.TERMINATE_PROCESS_TREE,
    },
}
