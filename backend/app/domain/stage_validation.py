"""Domain rules for stage validation final install and deterministic static checks.

S3-F10 capability: clean install verification and static analysis of transformed
Angular code.  Detached from routes, LLM agents, and persistence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StageValidationError(ValueError):
    """Raised when validation logic detects an illegal operation."""


class InstallStaticCheckType(str, Enum):
    """Types of static checks that can be performed."""
    TYPESCRIPT_COMPILE = "typescript_compile"
    TEMPLATE_CHECK = "template_check"
    IMPORT_RESOLUTION = "import_resolution"
    ANGULAR_COMPAT = "angular_compat"


class ValidationResultStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    NOT_CONFIGURED = "not_configured"


@dataclass(frozen=True)
class StaticCheckResult:
    check_type: InstallStaticCheckType
    status: ValidationResultStatus
    message: str = ""
    duration_ms: int = 0
    details: dict[str, Any] | None = None


@dataclass(frozen=True)
class ValidationResult:
    install_succeeded: bool = False
    install_duration_ms: int = 0
    install_output: str = ""
    check_results: tuple[StaticCheckResult, ...] = ()
    all_checks_passed: bool = False


class TypeScriptCheckAdapter:
    """Adapter for TypeScript compilation check."""
    CHECK_TYPE = InstallStaticCheckType.TYPESCRIPT_COMPILE

    def build_command(self, sandbox_path) -> dict[str, Any]:
        return {
            "executable": "npx",
            "arguments": ["tsc", "--noEmit", "--pretty"],
            "working_directory": str(sandbox_path),
        }


class AngularTemplateCheckAdapter:
    """Adapter for Angular template check."""
    CHECK_TYPE = InstallStaticCheckType.TEMPLATE_CHECK

    def build_command(self, sandbox_path) -> dict[str, Any]:
        return {
            "executable": "npx",
            "arguments": ["ng", "build", "--configuration=production"],
            "working_directory": str(sandbox_path),
        }


class ImportCheckAdapter:
    """Adapter for import resolution check."""
    CHECK_TYPE = InstallStaticCheckType.IMPORT_RESOLUTION

    def build_command(self, sandbox_path) -> dict[str, Any]:
        return {
            "executable": "npx",
            "arguments": ["madge", "--circular", "--extensions", "ts", "./src"],
            "working_directory": str(sandbox_path),
        }


class StageValidationService:
    """Domain logic for stage validation - aggregates install and static check results."""

    @staticmethod
    def aggregate_results(
        *,
        check_results: list[StaticCheckResult],
        install_succeeded: bool,
        install_duration_ms: int = 0,
        install_output: str = "",
    ) -> ValidationResult:
        all_passed = all(c.status is ValidationResultStatus.PASSED for c in check_results)
        return ValidationResult(
            install_succeeded=install_succeeded,
            install_duration_ms=install_duration_ms,
            install_output=install_output,
            check_results=tuple(check_results),
            all_checks_passed=install_succeeded and all_passed,
        )

    @staticmethod
    def aggregate_summary(result: ValidationResult) -> dict[str, Any]:
        return {
            "install_succeeded": result.install_succeeded,
            "install_duration_ms": result.install_duration_ms,
            "check_result_count": len(result.check_results),
            "all_checks_passed": result.all_checks_passed,
            "checks": [
                {
                    "type": c.check_type.value,
                    "status": c.status.value,
                    "message": c.message,
                }
                for c in result.check_results
            ],
            "overall": "passed" if result.all_checks_passed else "failed",
        }
