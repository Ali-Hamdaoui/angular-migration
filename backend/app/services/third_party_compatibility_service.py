"""Third-party dependency inventory extraction and compatibility scanning (V2 F15)."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.domain.dependency_compatibility import (
    ANGULAR_SCOPED_PACKAGES,
    TOOLCHAIN_PACKAGES,
    DependencyCompatibilityFinding,
    DependencyCompatibilityReport,
    DependencyInventoryItem,
)
from app.repositories.models import MigrationRunModel, MigrationStageModel, ThirdPartyCompatibilityReportModel
from app.repositories.session import session_scope


class ThirdPartyCompatibilityError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


_SEMVER = re.compile(r"(\d+)\.(\d+)\.(\d+)")


class ThirdPartyCompatibilityScanner:
    """Extract the dependency inventory and classify compatibility per stage target."""

    def __init__(
        self,
        *,
        session_scope_factory: Callable[[], AbstractContextManager] | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_scope = session_scope_factory or session_scope
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def extract_inventory(self, workspace: Path) -> list[DependencyInventoryItem]:
        """Extract the third-party dependency inventory (F15-01)."""
        package_json = workspace / "package.json"
        if not package_json.is_file():
            raise ThirdPartyCompatibilityError("PACKAGE_JSON_MISSING", "package.json is not present in the workspace")
        try:
            package = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            raise ThirdPartyCompatibilityError("PACKAGE_JSON_INVALID", "package.json is not valid JSON")
        if not isinstance(package, dict):
            raise ThirdPartyCompatibilityError("PACKAGE_JSON_INVALID", "package.json is not an object")
        resolved = self._resolved_versions(workspace)
        inventory: list[DependencyInventoryItem] = []
        for scope in ("dependencies", "devDependencies", "peerDependencies"):
            values = package.get(scope, {})
            if not isinstance(values, dict):
                continue
            for name, declared in values.items():
                if not isinstance(declared, str):
                    continue
                if name in ANGULAR_SCOPED_PACKAGES or name in TOOLCHAIN_PACKAGES:
                    continue
                inventory.append(
                    DependencyInventoryItem(
                        name=name, declared=declared,
                        resolved=resolved.get("versions", {}).get(name), scope=_scope_name(scope),
                    )
                )
        inventory.sort(key=lambda item: item.name)
        return inventory

    @staticmethod
    def _resolved_versions(workspace: Path) -> dict:
        """Resolved versions plus per-package @angular/core peer ranges from the lockfile."""
        lock = workspace / "package-lock.json"
        result: dict = {"versions": {}, "peers": {}}
        if not lock.is_file():
            return result
        try:
            payload = json.loads(lock.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return result
        packages = payload.get("packages", {}) if isinstance(payload, dict) else {}
        if not isinstance(packages, dict):
            return result
        for key, entry in packages.items():
            if not isinstance(entry, dict) or not key.startswith("node_modules/"):
                continue
            name = key[len("node_modules/"):]
            if "/" in name and not name.startswith("@"):
                continue
            version = entry.get("version")
            if isinstance(version, str) and name not in result["versions"]:
                result["versions"][name] = version
            peers = entry.get("peerDependencies")
            if isinstance(peers, dict):
                angular_range = peers.get("@angular/core")
                if isinstance(angular_range, str) and name not in result["peers"]:
                    result["peers"][name] = angular_range
        return result

    def scan_stage(self, workspace: Path, *, run_id: str, stage_id: str) -> DependencyCompatibilityReport:
        """Extract and classify the inventory for a stage target (F15-02/03)."""
        with self._session_scope() as session:
            stage = session.get(MigrationStageModel, stage_id)
            if stage is None:
                raise ThirdPartyCompatibilityError("STAGE_NOT_FOUND", f"Migration stage {stage_id} not found")
            source_major = _major(stage.source_version_family)
            target_major = _major(stage.target_version_family)
        inventory = self.extract_inventory(workspace)
        resolved = self._resolved_versions(workspace)
        findings = [self._classify(item, target_major, resolved.get("peers", {})) for item in inventory]
        blockers = tuple(f.name for f in findings if f.status in {"incompatible", "peer_conflict"})
        status = "blocked" if blockers else ("warnings" if any(f.status == "unknown" for f in findings) else "compatible")
        return DependencyCompatibilityReport(
            run_id=run_id, stage_id=stage_id, source_major=source_major, target_major=target_major,
            inventory=tuple(inventory), findings=tuple(findings), status=status, blockers=blockers,
        )

    @staticmethod
    def _classify(item: DependencyInventoryItem, target_major: int, peers: dict[str, str]) -> DependencyCompatibilityFinding:
        """Classify one dependency against the target Angular major.

        Uses the lockfile entry's ``@angular/core`` peer range when present: a
        range that excludes the target major is a peer conflict; a range that
        includes it is compatible; an unparseable range is unknown.  Without
        peer evidence, a resolved version is compatible; an unresolved one is
        unknown.
        """
        peer_range = peers.get(item.name)
        if peer_range:
            allows = _range_satisfies_major(peer_range, target_major)
            if allows is False:
                return DependencyCompatibilityFinding(
                    name=item.name, declared=item.declared, resolved=item.resolved,
                    target_major=target_major, status="peer_conflict",
                    detail=f"peer range {peer_range} does not allow Angular {target_major}",
                )
            if allows is True:
                return DependencyCompatibilityFinding(
                    name=item.name, declared=item.declared, resolved=item.resolved,
                    target_major=target_major, status="compatible",
                    detail=f"peer range {peer_range} allows Angular {target_major}",
                )
            return DependencyCompatibilityFinding(
                name=item.name, declared=item.declared, resolved=item.resolved,
                target_major=target_major, status="unknown",
                detail=f"peer range {peer_range} cannot be evaluated for Angular {target_major}",
            )
        if item.resolved is None:
            return DependencyCompatibilityFinding(
                name=item.name, declared=item.declared, resolved=None,
                target_major=target_major, status="unknown",
                detail="resolved version not found in lockfile and no peer evidence",
            )
        return DependencyCompatibilityFinding(
            name=item.name, declared=item.declared, resolved=item.resolved,
            target_major=target_major, status="compatible", detail="resolved version present",
        )

    def persist(self, run_id: str, report: DependencyCompatibilityReport) -> ThirdPartyCompatibilityReportModel:
        """Persist the per-stage compatibility report (F15-04)."""
        with self._session_scope() as session:
            if session.get(MigrationRunModel, run_id) is None:
                raise ThirdPartyCompatibilityError("RUN_NOT_FOUND", f"Migration run {run_id} not found")
            existing = session.scalar(
                select(ThirdPartyCompatibilityReportModel).where(
                    ThirdPartyCompatibilityReportModel.stage_id == report.stage_id,
                )
            )
            if existing is not None:
                return existing
            row = ThirdPartyCompatibilityReportModel(
                id=_report_id(report.stage_id),
                run_id=run_id,
                stage_id=report.stage_id,
                source_major=report.source_major,
                target_major=report.target_major,
                status=report.status,
                blockers=list(report.blockers),
                inventory=[item.model_dump(mode="json") for item in report.inventory],
                findings=[finding.model_dump(mode="json") for finding in report.findings],
                created_at=self._now_provider(),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    def list_stage_reports(self, stage_id: str) -> list[ThirdPartyCompatibilityReportModel]:
        with self._session_scope() as session:
            return list(
                session.scalars(
                    select(ThirdPartyCompatibilityReportModel)
                    .where(ThirdPartyCompatibilityReportModel.stage_id == stage_id)
                    .order_by(ThirdPartyCompatibilityReportModel.created_at.desc())
                ).all()
            )


def _scope_name(scope: str) -> str:
    if scope == "devDependencies":
        return "devDependency"
    if scope == "peerDependencies":
        return "peerDependency"
    return "dependency"


def _range_satisfies_major(peer_range: str, target_major: int) -> bool | None:
    """Does a peer range (e.g. '^17.0.0', '>=16 <19', '^17.0.0 || ^18.0.0') allow a major?

    Returns True/False when determinable, None when the range syntax cannot be
    evaluated (callers treat None as unknown, never as compatible).
    """
    range_text = peer_range.strip()
    if not range_text:
        return None
    # OR ranges: any alternative satisfying the major makes the range satisfy it.
    if "||" in range_text:
        alternatives = [part.strip() for part in range_text.split("||")]
        if not alternatives:
            return None
        results = [_single_range_satisfies(part, target_major) for part in alternatives]
        if any(result is True for result in results):
            return True
        if all(result is False for result in results):
            return False
        return None
    return _single_range_satisfies(range_text, target_major)


def _single_range_satisfies(range_text: str, target_major: int) -> bool | None:
    if range_text.startswith("^") or range_text.startswith("~"):
        match = _SEMVER.search(range_text)
        if not match:
            return None
        return int(match.group(1)) == target_major
    if " - " in range_text:
        low, high = range_text.split(" - ", 1)
        low_match = _SEMVER.search(low)
        high_match = _SEMVER.search(high)
        if not low_match or not high_match:
            return None
        return int(low_match.group(1)) <= target_major <= int(high_match.group(1))
    comparisons = re.findall(r"(>=|<=|>|<|=)\s*(\d+)\.\d+\.\d+", range_text)
    if comparisons:
        allowed = True
        for operator, major_text in comparisons:
            major = int(major_text)
            if operator in {">=", ">"} and target_major < major:
                allowed = False
            if operator in {"<=", "<"} and target_major > major:
                allowed = False
        return allowed
    match = _SEMVER.search(range_text)
    if match and not any(c in range_text for c in "><^~|-,"):
        return int(match.group(1)) == target_major
    return None


def _major(family: str | None) -> int:
    if not family:
        return 0
    try:
        return int(family.removeprefix("angular-").removesuffix(".x"))
    except ValueError:
        return 0


def _report_id(stage_id: str) -> str:
    import hashlib

    return "tpc-" + hashlib.sha256(stage_id.encode()).hexdigest()[:24]
