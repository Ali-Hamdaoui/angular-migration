"""PATH-independent runtime resolver authority (V2 F01-02).

The authority resolves node/npm/npx executables from the configured runtime
matrix only -- never from PATH -- and returns immutable, checksum-bound
``RuntimeExecutableDescriptor`` facts.  Deterministic and free of business
state; version probing runs through the command worker supplied by the
application layer.

This service owns NO persistence.  Evidence persistence is the runtime
evidence application service (F01-04).
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.domain.runtime_execution import (
    RuntimeExecutableDescriptor,
    RuntimeExecutableKind,
    RuntimeRequirement,
    RuntimeRequirementBinding,
)


def sha256_of(path: Path) -> str:
    """SHA-256 hex digest of an executable file's bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


VersionProbe = Callable[[Path], str | None]


@dataclass(frozen=True)
class RuntimeMatrix:
    """Configured PATH-independent runtime roots."""

    node_install_root: Path
    angular_cli_root: Path

    @property
    def probe_roots(self) -> frozenset[Path]:
        return frozenset({self.node_install_root, self.angular_cli_root})


class RuntimeResolverAuthority:
    """Deterministic resolver that never consults PATH."""

    def __init__(
        self,
        matrix: RuntimeMatrix,
        *,
        probe: VersionProbe,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._matrix = matrix
        self._probe = probe
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def discover(self) -> list[RuntimeExecutableDescriptor]:
        """Enumerate every node/npm/npx executable in the runtime matrix."""
        descriptors: list[RuntimeExecutableDescriptor] = []
        for version_dir in sorted(self._matrix.node_install_root.glob("v*[0-9].*[0-9].*[0-9]"), key=lambda p: p.name):
            if not version_dir.is_dir():
                continue
            installation_root = version_dir
            bin_dir = version_dir / "bin"
            executable_root, executable_names = (
                (bin_dir, {
                    RuntimeExecutableKind.NODE: "node",
                    RuntimeExecutableKind.NPM: "npm",
                    RuntimeExecutableKind.NPX: "npx",
                })
                if bin_dir.is_dir()
                else (version_dir, {
                    RuntimeExecutableKind.NODE: "node.exe",
                    RuntimeExecutableKind.NPM: "npm.cmd",
                    RuntimeExecutableKind.NPX: "npx.cmd",
                })
            )
            for kind, executable_name in executable_names.items():
                path = executable_root / executable_name
                if not path.is_file():
                    continue
                descriptor = self._build_descriptor(
                    kind=kind,
                    executable_name=executable_name,
                    path=path,
                    installation_root=installation_root,
                    source="nvm",
                    runtime_id=version_dir.name,
                )
                descriptors.append(descriptor)
        return descriptors

    def resolve(self, requirements: list[RuntimeRequirement]) -> list[RuntimeRequirementBinding]:
        """Resolve each requirement deterministically to a binding."""
        descriptors = self.discover()
        bindings: list[RuntimeRequirementBinding] = []
        grouped: dict[str, list[RuntimeRequirement]] = {}
        for requirement in requirements:
            grouped.setdefault(requirement.runtime_id, []).append(requirement)
        for group in grouped.values():
            paired = self._best_paired_install(group, descriptors) if len(group) > 1 else None
            for requirement in group:
                match = paired.get(requirement.kind) if paired is not None else self._best_match(requirement, descriptors)
                if match is None:
                    bindings.append(
                        RuntimeRequirementBinding(
                            requirement=requirement,
                            blocked_reason=f"no {requirement.kind.value} candidate satisfies the requirement",
                            resolved_at=self._now_provider(),
                        )
                    )
                    continue
                bindings.append(RuntimeRequirementBinding(requirement=requirement, descriptor=match, resolved_at=self._now_provider()))
        return bindings

    def _best_paired_install(self, requirements, descriptors):
        candidates = []
        for runtime_id in sorted({item.runtime_id for item in descriptors if item.runtime_id}):
            matches = {
                requirement.kind: next(
                    (item for item in descriptors if item.runtime_id == runtime_id and requirement.satisfied_by(item)),
                    None,
                )
                for requirement in requirements
            }
            if all(matches.values()):
                node = matches.get(RuntimeExecutableKind.NODE)
                candidates.append((node.version_exact if node else "", runtime_id, matches))
        return max(candidates, key=lambda item: (item[0], item[1]))[2] if candidates else {}

    def _build_descriptor(
        self,
        *,
        kind: RuntimeExecutableKind,
        executable_name: str,
        path: Path,
        installation_root: Path,
        source: str,
        runtime_id: str,
    ) -> RuntimeExecutableDescriptor:
        version = self._probe(path)
        return RuntimeExecutableDescriptor(
            kind=kind,
            executable_name=executable_name,
            resolved_path=str(path),  # keep the canonical executable location (symlink resolved at execution)
            version_exact=version,
            sha256=sha256_of(path),
            operating_system=_operating_system(),
            architecture=_architecture(),
            installation_root=str(installation_root),
            source=source,
            runtime_id=runtime_id,
            probed_at=self._now_provider(),
        )

    @staticmethod
    def _best_match(requirement: RuntimeRequirement, descriptors: list[RuntimeExecutableDescriptor]) -> RuntimeExecutableDescriptor | None:
        candidates = [item for item in descriptors if requirement.satisfied_by(item)]
        if not candidates:
            return None
        # Pairing: a requirement naming a runtime installation (e.g. ``node18``)
        # must bind npm/npx from that same installation, never the newest install
        # that happens to satisfy the version range.
        paired = [item for item in candidates if RuntimeResolverAuthority._same_install(requirement.runtime_id, item.runtime_id)]
        if paired:
            candidates = paired

        def key(item: RuntimeExecutableDescriptor) -> tuple[bool, str, str]:
            return (item.version_exact == requirement.version_exact, item.version_exact or "", item.resolved_path)

        return max(candidates, key=key)

    @staticmethod
    def _same_install(requirement_runtime_id: str, candidate_runtime_id: str | None) -> bool:
        if candidate_runtime_id is None:
            return False
        if requirement_runtime_id == candidate_runtime_id:
            return True
        # ``node18`` pairs with install ``v18.20.8``.
        if requirement_runtime_id.startswith("node") and candidate_runtime_id.startswith("v"):
            requirement_major = requirement_runtime_id[len("node"):]
            candidate_major = candidate_runtime_id[1:].split(".", 1)[0]
            return requirement_major == candidate_major
        return False


def _operating_system() -> str:
    import platform

    return platform.system().lower()


def _architecture() -> str:
    import platform

    return platform.machine().lower()
