"""Factory-owned tooling policy, separate from Angular compatibility truth."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ToolingPolicy:
    policy_version: str
    source_family: str
    target_family: str
    requirements: dict[str, str]


class ProvenStageToolingPolicy:
    """Resolve execution-tool requirements from version families, not versions."""

    VERSION = "proven-stage-tooling-v1"
    _ANGULAR_FAMILY = re.compile(r"^angular-(\d+)\.x$")

    def resolve(self, source_family: str, target_family: str) -> dict[str, str]:
        source_major = self._major(source_family)
        target_major = self._major(target_family)
        if source_major is None or target_major is None or source_major < 11 or target_major < 12:
            return {}
        return {"karma": "~6.4.4"}

    def policy(self, source_family: str, target_family: str) -> ToolingPolicy:
        return ToolingPolicy(
            policy_version=self.VERSION,
            source_family=source_family,
            target_family=target_family,
            requirements=self.resolve(source_family, target_family),
        )

    def apply(self, manifest: dict, source_family: str, target_family: str) -> bool:
        requirements = self.resolve(source_family, target_family)
        changed = False
        for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
            values = manifest.get(section)
            if not isinstance(values, dict):
                continue
            for package, version in requirements.items():
                if package in values and values[package] != version:
                    values[package] = version
                    changed = True
        return changed

    @classmethod
    def _major(cls, family: str) -> int | None:
        match = cls._ANGULAR_FAMILY.fullmatch(str(family))
        return int(match.group(1)) if match else None
