"""Catalogue certification pipeline service (V2 F30).

For each catalogue entry the pipeline materializes a deterministic per-entry
fixture workspace and certifies the entry only when the catalogue records
validated runtime proof: PASS promotes the entry to certified; FAIL rejects
it with durable evidence.  Deterministic: identical fixture + identical
catalogue -> identical outcome.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.domain.catalogue_certification import (
    CatalogueCertificationCase,
    CatalogueCertificationOutcome,
    CatalogueCertificationRun,
    CertificationStatus,
)
from app.repositories.models import CatalogueCertificationModel
from app.repositories.session import session_scope
from app.services.compatibility_catalogue_provider import CompatibilityCatalogueProvider


class CatalogueCertificationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def build_fixture_workspace(root: Path, source_family: str, target_family: str) -> Path:
    """Materialize a deterministic per-entry runtime fixture (F30-02)."""
    source_major = int(source_family.removeprefix("angular-").removesuffix(".x"))
    target_major = int(target_family.removeprefix("angular-").removesuffix(".x"))
    workspace = root / f"fixture-{source_major}-to-{target_major}"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "package.json").write_text(
        "{\n"
        f'  "name": "fixture-angular-{source_major}-to-{target_major}",\n'
        f'  "version": "1.0.0",\n'
        f'  "dependencies": {{\n'
        f'    "@angular/core": "{source_major}.0.0",\n'
        f'    "@angular/cli": "{source_major}.0.0"\n'
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    (workspace / "src").mkdir(exist_ok=True)
    (workspace / "src" / "main.ts").write_text(
        "import { Component } from '@angular/core';\n"
        f"@Component({{ selector: 'app-root', template: '<h1>fixture {source_major}->{target_major}</h1>' }})\n"
        f"export class AppComponent {{\n"
        f"  target: string = '{target_major}.0.0';\n"
        "}\n",
        encoding="utf-8",
    )
    return workspace


class CatalogueCertificationPipeline:
    """Deterministic certification pipeline runner (F30-01)."""

    def __init__(
        self,
        *,
        catalogue_provider: CompatibilityCatalogueProvider | None = None,
        session_scope_factory: Callable[[], AbstractContextManager] | None = None,
        now_provider: Callable[[], datetime] | None = None,
        allowed_roots: list[Path] | None = None,
    ) -> None:
        self._catalogue = catalogue_provider or CompatibilityCatalogueProvider()
        self._session_scope = session_scope_factory or session_scope
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
        self._allowed_roots = [Path(path).resolve() for path in (allowed_roots or [])]

    def _assert_fixture_root_allowed(self, fixture_root: Path) -> None:
        """Fail closed before any fixture is written (review hardening)."""
        if not self._allowed_roots:
            return
        resolved = fixture_root.resolve(strict=False)
        if not any(_within_root(resolved, root) for root in self._allowed_roots):
            raise CatalogueCertificationError(
                "FIXTURE_ROOT_NOT_ALLOWED",
                f"fixture_root {fixture_root} is outside the allowed source roots",
            )

    def run(
        self,
        *,
        fixture_root: Path,
        cases: list[CatalogueCertificationCase] | None = None,
        run_id: str | None = None,
    ) -> CatalogueCertificationRun:
        """Run the pipeline over the catalogue entries and certify/reject (F30-01/03)."""
        self._assert_fixture_root_allowed(fixture_root)
        catalogue = self._catalogue.load()
        run_id = run_id or f"certrun-{uuid4().hex[:12]}"
        if cases is None:
            cases = [
                CatalogueCertificationCase(
                    case_id=f"{entry.source_family}-to-{entry.target_family}",
                    source_family=entry.source_family,
                    target_family=entry.target_family,
                )
                for entry in catalogue.entries
            ]
        outcomes = [self._certify_entry(run_id, fixture_root, case, catalogue.version) for case in cases]
        certified = [o for o in outcomes if o.status is CertificationStatus.CERTIFIED]
        run = CatalogueCertificationRun(
            run_id=run_id,
            catalogue_version=catalogue.version,
            outcomes=tuple(outcomes),
            certified_count=len(certified),
            rejected_count=len(outcomes) - len(certified),
            deterministic=True,
            ran_at=self._now_provider(),
        ).bind_checksum()
        return run

    def _certify_entry(
        self,
        run_id: str,
        fixture_root: Path,
        case: CatalogueCertificationCase,
        catalogue_version: str,
    ) -> CatalogueCertificationOutcome:
        """Certify one entry: fixture -> chain -> runtime proof (F30-02/03)."""
        evidence: list[str] = []
        runtime_proof: list[tuple[str, str]] = []
        workspace = build_fixture_workspace(fixture_root, case.source_family, case.target_family)
        evidence.append(f"fixture_materialized:{workspace.name}")
        if not (workspace / "package.json").is_file():
            evidence.append("fixture_package_missing")
            return self._reject(case, evidence, "fixture could not be materialized")
        catalogue = self._catalogue.load(catalogue_version)
        entry = catalogue.entry_for(case.source_family, case.target_family)
        if entry is None:
            evidence.append("catalogue_entry_missing")
            return self._reject(case, evidence, f"no catalogue entry for {case.source_family} -> {case.target_family}")
        evidence.append(f"catalogue_entry:{entry.support_level}")
        if entry.support_level == "blocked":
            evidence.append("entry_blocked")
            return self._reject(case, evidence, "catalogue marks the transition as blocked")
        # Runtime-proven certification (F30-03): an entry is certified only
        # when its runtime profiles are actually recorded/validated.  A node
        # minimum alone is documentation, not proof — unproven entries are
        # rejected with durable evidence.
        if entry.certification_status == "certified" and entry.validated_runtime_profiles:
            runtime_proof = list(entry.validated_runtime_profiles)
            evidence.append("runtime_proof:certified_profiles")
            return self._certify(case, runtime_proof, evidence, f"certified against {catalogue_version}")
        evidence.append("runtime_profile_missing")
        return self._reject(
            case,
            evidence,
            f"entry {case.source_family} -> {case.target_family} has no validated runtime proof to certify",
        )

    @staticmethod
    def _certify(case, runtime_proof, evidence, reason) -> CatalogueCertificationOutcome:
        return CatalogueCertificationOutcome(
            case_id=case.case_id, source_family=case.source_family, target_family=case.target_family,
            status=CertificationStatus.CERTIFIED, runtime_proof=tuple(tuple(p) for p in runtime_proof),
            evidence=tuple(evidence), reason=reason,
        ).bind_checksum()

    @staticmethod
    def _reject(case, evidence, reason) -> CatalogueCertificationOutcome:
        return CatalogueCertificationOutcome(
            case_id=case.case_id, source_family=case.source_family, target_family=case.target_family,
            status=CertificationStatus.REJECTED, runtime_proof=(), evidence=tuple(evidence), reason=reason,
        ).bind_checksum()

    def persist(self, run: CatalogueCertificationRun) -> list[CatalogueCertificationModel]:
        """Persist the certification evidence and audit (F30-04)."""
        now = self._now_provider()
        with self._session_scope() as session:
            stored: list[CatalogueCertificationModel] = []
            for outcome in run.outcomes:
                record_id = "cert-" + hashlib.sha256(
                    f"{outcome.source_family}:{outcome.target_family}:{run.run_id}".encode()
                ).hexdigest()[:24]
                existing = session.get(CatalogueCertificationModel, record_id)
                if existing is not None:
                    stored.append(existing)
                    continue
                model = CatalogueCertificationModel(
                    id=record_id,
                    run_id=run.run_id,
                    source_family=outcome.source_family,
                    target_family=outcome.target_family,
                    status=outcome.status.value,
                    runtime_proof=[list(p) for p in outcome.runtime_proof],
                    evidence=list(outcome.evidence),
                    reason=outcome.reason,
                    catalogue_version=run.catalogue_version,
                    deterministic=run.deterministic,
                    checksum=outcome.checksum,
                    ran_at=run.ran_at,
                    created_at=now,
                )
                session.add(model)
                stored.append(model)
            session.commit()
        return stored

    def list_certifications(self, *, source: str | None = None, target: str | None = None) -> list[CatalogueCertificationModel]:
        with self._session_scope() as session:
            query = select(CatalogueCertificationModel)
            if source:
                query = query.where(CatalogueCertificationModel.source_family == source)
            if target:
                query = query.where(CatalogueCertificationModel.target_family == target)
            return list(session.scalars(query.order_by(CatalogueCertificationModel.created_at.desc())).all())


def _within_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
