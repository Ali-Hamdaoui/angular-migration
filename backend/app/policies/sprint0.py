"""Injectable Sprint 0 policy defaults."""

from dataclasses import dataclass, field
from typing import Literal


MigrationSupportLevel = Literal[
    "officially_supported",
    "historical_validated",
    "historical_experimental",
    "blocked",
]


@dataclass(frozen=True)
class CommandAllowlistPolicy:
    version_commands: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("python", ("--version",)),
        ("node", ("--version",)),
        ("npm", ("--version",)),
        ("git", ("--version",)),
    )
    shell_allowed: bool = False
    network_profile: str = "none"


@dataclass(frozen=True)
class InstallScriptPolicy:
    lifecycle_scripts_allowed: bool = False
    package_downloads_allowed: bool = False
    allowed_script_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChangedFileSensitivityPolicy:
    high_risk_globs: tuple[str, ...] = (
        "**/auth/**",
        "**/interceptors/**",
        "**/guards/**",
        "**/environment*",
        "**/*validator*",
    )
    blocked_globs: tuple[str, ...] = ("**/.env*", "**/*secret*", "**/*credential*")


@dataclass(frozen=True)
class AutoApprovalPolicy:
    enabled_by_default: bool = False
    forbidden_risk_levels: tuple[str, ...] = ("high", "critical")
    requires_current_gate_checksum: bool = True


@dataclass(frozen=True)
class TopologySupportPolicy:
    allowed_package_managers: tuple[str, ...] = ("npm",)
    allowed_source_families: tuple[str, ...] = ("angular-18.x",)
    allowed_target_families: tuple[str, ...] = ("angular-21.x",)
    default_support_level: MigrationSupportLevel = "historical_experimental"


@dataclass(frozen=True)
class Sprint0Policies:
    topology: TopologySupportPolicy = field(default_factory=TopologySupportPolicy)
    commands: CommandAllowlistPolicy = field(default_factory=CommandAllowlistPolicy)
    install_scripts: InstallScriptPolicy = field(default_factory=InstallScriptPolicy)
    changed_files: ChangedFileSensitivityPolicy = field(default_factory=ChangedFileSensitivityPolicy)
    auto_approval: AutoApprovalPolicy = field(default_factory=AutoApprovalPolicy)


_DEFAULT_POLICIES = Sprint0Policies()


def get_sprint0_policies() -> Sprint0Policies:
    return _DEFAULT_POLICIES
