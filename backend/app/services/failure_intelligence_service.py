"""Failure intelligence service: grouping, root cause, dependency graph (V2 F19)."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.domain.failure_intelligence import (
    FailureDependencyEdge,
    FailureDependencyGraph,
    FailureGroup,
    FailureRootCause,
)
from app.repositories.models import FailureDiagnosticPackModel, FailureIntelligenceModel
from app.repositories.session import session_scope


class FailureIntelligenceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


#: Deterministic root-cause precedence: the earliest dependency in a causal
#: chain is the root cause.
_ROOT_CAUSE_PRECEDENCE = (
    "environment", "dependency", "command", "state", "policy", "transport", "llm", "workflow", "unknown",
)

class FailureIntelligenceService:
    """Group failures, resolve root causes, and model dependencies (F19)."""

    def __init__(
        self,
        *,
        session_scope_factory: Callable[[], AbstractContextManager] | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_scope = session_scope_factory or session_scope
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    @staticmethod
    def stable_group_key(fault_code: str, taxonomy: str, message: str) -> str:
        """Deterministic stable group key: taxonomy + code + normalized signature.

        The signature is the first normalized line of the failure message so
        identical failures in the same taxonomy/code bucket group together.
        """
        signature = _signature(message)
        canonical = f"{taxonomy}:{fault_code}:{signature}"
        return "fg-" + hashlib.sha256(canonical.encode()).hexdigest()[:24]

    def group(self, packs: list[dict[str, Any]]) -> list[FailureGroup]:
        """Group diagnostic packs into stable groups (F19-02)."""
        groups: dict[str, dict[str, Any]] = {}
        for pack in packs:
            fault_code = pack.get("fault_code") or "UNKNOWN"
            taxonomy = pack.get("category") or "unknown"
            message = pack.get("message") or ""
            occurred = pack.get("created_at") or self._now_provider()
            key = self.stable_group_key(fault_code, taxonomy, message)
            entry = groups.setdefault(
                key,
                {"key": key, "taxonomy": taxonomy, "codes": set(), "count": 0, "first": occurred, "last": occurred, "messages": []},
            )
            entry["codes"].add(fault_code)
            entry["count"] += 1
            entry["messages"].append(message)
            entry["first"] = min(entry["first"], occurred)
            entry["last"] = max(entry["last"], occurred)
        result = []
        for entry in groups.values():
            group = FailureGroup(
                group_key=entry["key"],
                taxonomy=entry["taxonomy"],
                fault_codes=tuple(sorted(entry["codes"])),
                member_count=entry["count"],
                first_seen=entry["first"],
                last_seen=entry["last"],
                signature=entry["messages"][0][:200] if entry["messages"] else "",
            ).bind_checksum()
            result.append(group)
        result.sort(key=lambda g: g.group_key)
        return result

    def resolve_root_cause(self, group: FailureGroup, graph: FailureDependencyGraph | None = None) -> FailureRootCause:
        """Deterministic root cause for a group (F19-03).

        When the group has inbound dependency edges, the root cause resolves to
        the earliest-precedence upstream group; otherwise it is the group's own
        dominant code.
        """
        root = group
        if graph is not None:
            visited = {group.group_key}
            current = group
            while True:
                inbound = [edge.depends_on for edge in graph.edges if edge.dependent == current.group_key]
                candidates = [n for n in graph.nodes if n.group_key in inbound and n.group_key not in visited]
                if not candidates:
                    break
                next_root = min(candidates, key=lambda n: (_precedence(n.taxonomy), n.first_seen))
                visited.add(next_root.group_key)
                current = next_root
            root = current
        taxonomy = root.taxonomy
        code = root.fault_codes[0] if root.fault_codes else "UNKNOWN"
        confidence = "high" if taxonomy in {"environment", "dependency"} else "medium"
        explanation = f"{taxonomy} failure {code} is the deterministic root cause of group {group.group_key}"
        return FailureRootCause(
            group_key=group.group_key,
            root_cause_code=code,
            taxonomy=taxonomy,
            explanation=explanation,
            confidence=confidence,
            contributing_codes=root.fault_codes,
        )

    def build_dependency_graph(self, groups: list[FailureGroup]) -> FailureDependencyGraph:
        """Model dependency edges between failure groups (F19-04).

        A group whose taxonomy appears earlier in the causal precedence is a
        candidate blocker for groups of later taxonomies, and a blocker is only
        linked when it occurred at or before the dependent (time guard).
        """
        edges: list[FailureDependencyEdge] = []
        for blocker in groups:
            for dependent in groups:
                if blocker.group_key == dependent.group_key:
                    continue
                if _precedence(blocker.taxonomy) >= _precedence(dependent.taxonomy):
                    continue
                if blocker.first_seen > dependent.last_seen:
                    continue
                edges.append(
                    FailureDependencyEdge(
                        depends_on=blocker.group_key,
                        dependent=dependent.group_key,
                        reason=f"{blocker.taxonomy} failure precedes {dependent.taxonomy} failure",
                    )
                )
        graph = FailureDependencyGraph(nodes=tuple(groups), edges=tuple(sorted(edges, key=lambda e: (e.depends_on, e.dependent))))
        return graph.bind_checksum()

    def intelligence_for_run(self, run_id: str) -> dict[str, Any]:
        """Build the full intelligence layer for a run's diagnostic packs."""
        with self._session_scope() as session:
            packs = session.scalars(
                select(FailureDiagnosticPackModel)
                .where(FailureDiagnosticPackModel.run_id == run_id)
                .order_by(FailureDiagnosticPackModel.created_at.asc())
            ).all()
        payloads = [
            {"fault_code": p.fault_code, "category": p.category, "message": p.message, "created_at": p.created_at}
            for p in packs
        ]
        groups = self.group(payloads)
        graph = self.build_dependency_graph(groups)
        roots = {g.group_key: self.resolve_root_cause(g, graph) for g in groups}
        return {"groups": groups, "root_causes": roots, "graph": graph}

    def persist(self, run_id: str, intelligence: dict[str, Any]) -> FailureIntelligenceModel:
        """Persist the intelligence snapshot (F19-04 evidence)."""
        with self._session_scope() as session:
            existing = session.scalar(
                select(FailureIntelligenceModel).where(
                    FailureIntelligenceModel.run_id == run_id,
                    FailureIntelligenceModel.checksum == intelligence["graph"].checksum,
                )
            )
            if existing is not None:
                return existing
            row = FailureIntelligenceModel(
                id="fi-" + hashlib.sha256(f"{run_id}:{intelligence['graph'].checksum}".encode()).hexdigest()[:24],
                run_id=run_id,
                groups=[g.model_dump(mode="json") for g in intelligence["groups"]],
                root_causes={k: v.model_dump(mode="json") for k, v in intelligence["root_causes"].items()},
                graph=intelligence["graph"].model_dump(mode="json"),
                checksum=intelligence["graph"].checksum,
                created_at=self._now_provider(),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    def get_run_intelligence(self, run_id: str) -> FailureIntelligenceModel | None:
        with self._session_scope() as session:
            return session.scalar(
                select(FailureIntelligenceModel)
                .where(FailureIntelligenceModel.run_id == run_id)
                .order_by(FailureIntelligenceModel.created_at.desc())
                .limit(1)
            )

def _signature(message: str) -> str:
    text = message.strip()
    first_line = text.splitlines()[0] if text else ""
    normalized = re.sub(r"0x[0-9a-fA-F]{6,}", "0x[ADDR]", first_line)[:200]
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def _precedence(taxonomy: str) -> int:
    return _ROOT_CAUSE_PRECEDENCE.index(taxonomy) if taxonomy in _ROOT_CAUSE_PRECEDENCE else len(_ROOT_CAUSE_PRECEDENCE)
