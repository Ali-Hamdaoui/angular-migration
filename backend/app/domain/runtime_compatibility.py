"""Shared, fail-closed runtime compatibility classification."""

from __future__ import annotations

from typing import Literal

from app.domain.execution_profile import Version

RuntimeCompatibilityClass = Literal["EXACT_CERTIFIED", "RANGE_COMPATIBLE", "UNSUPPORTED"]


def classify_runtime_versions(
    *,
    node_exact: str | None,
    npm_exact: str | None,
    npx_exact: str | None,
    validated_runtime_profiles: tuple[tuple[str, str], ...],
    source_node_ranges: tuple[str, ...],
    target_node_ranges: tuple[str, ...],
) -> RuntimeCompatibilityClass:
    node = Version.parse(node_exact or "")
    npm = Version.parse(npm_exact or "")
    if node is None or npm is None:
        return "UNSUPPORTED"
    if any(str(node) == known_node and str(npm) == known_npm for known_node, known_npm in validated_runtime_profiles):
        return "EXACT_CERTIFIED"
    npx = Version.parse(npx_exact or "")
    if npx is None:
        return "UNSUPPORTED"
    if not source_node_ranges or not target_node_ranges:
        return "UNSUPPORTED"
    if _satisfies_any(node, source_node_ranges) and _satisfies_any(node, target_node_ranges):
        return "RANGE_COMPATIBLE"
    return "UNSUPPORTED"


def _satisfies_any(version: Version, ranges: tuple[str, ...]) -> bool:
    return any(_satisfies_caret(version, value) for value in ranges)


def _satisfies_caret(version: Version, value: str) -> bool:
    if not value.startswith("^"):
        return False
    minimum = Version.parse(value[1:])
    return bool(minimum and version.at_least(minimum) and version.major == minimum.major)
