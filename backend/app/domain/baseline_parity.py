"""Deterministic baseline parity anchors for S1-F13.

The builders in this module inspect already-produced baseline evidence and the
immutable baseline sandbox.  They do not execute project code and do not make
functional-parity claims.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "baseline-parity-v1"
PARSER_VERSION = "baseline-parsers-v1"


class EvidenceConfidence(str, Enum):
    MACHINE_PROVEN = "machine_proven"
    USER_ATTESTED_ONLY = "user_attested_only"
    NOT_CONFIGURED = "not_configured"
    BLOCKED_BY_ENVIRONMENT = "blocked_by_environment"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class FailureFingerprint:
    fingerprint: str
    group: str
    kind: str
    message: str
    origin: str = "pre-existing"
    severity: str = "error"
    count: int = 1
    confidence: EvidenceConfidence = EvidenceConfidence.MACHINE_PROVEN
    parser_version: str = PARSER_VERSION
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class BaselineAnchor:
    name: str
    value: Any
    confidence: EvidenceConfidence
    schema_version: str = SCHEMA_VERSION
    source: str | None = None


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _normalise_message(message: str) -> str:
    value = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", message)
    value = value.replace("\\", "/")
    value = re.sub(r"[A-Za-z]:/[^\s:]+", "<path>", value)
    value = re.sub(r"/(?:[^\s/:]+/)+[^\s:]+", "<path>", value)
    value = re.sub(r"\b\d+\b", "<n>", value)
    return " ".join(value.lower().split())


class BaselineFailureFingerprintService:
    """Normalise diagnostics and assign reproducible baseline identities."""

    def fingerprint(
        self,
        *,
        kind: str,
        message: str,
        group: str | None = None,
        severity: str = "error",
        confidence: EvidenceConfidence = EvidenceConfidence.MACHINE_PROVEN,
        parser_version: str = PARSER_VERSION,
    ) -> FailureFingerprint:
        normalized = _normalise_message(message)
        failure_group = group or self._group(kind, normalized)
        identity = _stable_json({"kind": kind, "group": failure_group, "message": normalized, "parser_version": parser_version})
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        return FailureFingerprint(
            fingerprint=f"sha256:{digest}", kind=kind, group=failure_group,
            message=normalized, severity=severity, confidence=confidence,
            parser_version=parser_version,
        )

    def from_diagnostics(self, diagnostics: Iterable[Mapping[str, Any]]) -> list[FailureFingerprint]:
        grouped: dict[str, FailureFingerprint] = {}
        for diagnostic in diagnostics:
            item = self.fingerprint(
                kind=str(diagnostic.get("kind", "unknown")),
                message=str(diagnostic.get("message", "")),
                group=diagnostic.get("group"),
                severity=str(diagnostic.get("severity", "error")),
                confidence=EvidenceConfidence(diagnostic.get("confidence", EvidenceConfidence.MACHINE_PROVEN)),
                parser_version=str(diagnostic.get("parser_version", PARSER_VERSION)),
            )
            grouped[item.fingerprint] = FailureFingerprint(**{**asdict(item), "confidence": item.confidence})
        counts: dict[str, int] = {}
        for diagnostic in diagnostics:
            item = self.fingerprint(kind=str(diagnostic.get("kind", "unknown")), message=str(diagnostic.get("message", "")), group=diagnostic.get("group"), parser_version=str(diagnostic.get("parser_version", PARSER_VERSION)))
            counts[item.fingerprint] = counts.get(item.fingerprint, 0) + 1
        return [FailureFingerprint(**{**asdict(item), "confidence": item.confidence, "count": counts[item.fingerprint]}) for item in grouped.values()]

    @staticmethod
    def _group(kind: str, message: str) -> str:
        if "timeout" in message:
            return f"{kind}:timeout"
        if "syntax" in message or "parse" in message:
            return f"{kind}:syntax"
        return f"{kind}:failure"


class RouteInventoryBuilder:
    """Build a deliberately shallow route inventory from Angular source files."""

    _ROUTE = re.compile(r"\bpath\s*:\s*(['\"])(.*?)\1")
    _LAZY = re.compile(r"loadChildren\s*:\s*([^,}\n]+)")

    def build(self, workspace: Path) -> BaselineAnchor:
        routes: list[dict[str, Any]] = []
        angular = self._json(workspace / "angular.json")
        source_roots = self._source_roots(workspace, angular)
        for source_root in source_roots:
            for path in sorted(source_root.rglob("*.ts")):
                if any(part in {"node_modules", "dist", ".angular", "coverage"} for part in path.parts):
                    continue
                try:
                    content = path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                for match in self._ROUTE.finditer(content):
                    entry: dict[str, Any] = {"path": match.group(2), "file": path.relative_to(workspace).as_posix()}
                    lazy = self._LAZY.search(content, match.end())
                    if lazy:
                        entry["lazy_loader_indicator"] = lazy.group(1).strip()
                    routes.append(entry)
        return BaselineAnchor("routes", routes, EvidenceConfidence.MACHINE_PROVEN, source="angular.json/typescript")

    @staticmethod
    def _json(path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    @staticmethod
    def _source_roots(workspace: Path, angular: dict[str, Any] | None) -> list[Path]:
        if not angular or not isinstance(angular.get("projects"), dict):
            return [workspace]
        roots: list[Path] = []
        for project in angular["projects"].values():
            if isinstance(project, dict) and isinstance(project.get("sourceRoot"), str):
                roots.append(workspace / project["sourceRoot"])
        return roots or [workspace]


class BackendContractSnapshotBuilder:
    """Capture backend integration indicators without copying source contents."""

    _URL = re.compile(r"(?:apiUrl|apiRoot|baseUrl|baseURL|API_URL)\s*[:=]\s*[('\"]([^('\"]+)")
    _ENDPOINT = re.compile(r"(?:http(?:s)?|api|endpoint|url)[A-Za-z0-9_]*\s*[:=]\s*[('\"]([^('\"]+)")

    def build(self, workspace: Path) -> BaselineAnchor:
        files: list[str] = []
        api_roots: set[str] = set()
        proxy_files: list[str] = []
        endpoint_indicators: list[dict[str, str]] = []
        auth_files: list[str] = []
        for path in sorted(workspace.rglob("*")):
            if not path.is_file() or any(part in {"node_modules", "dist", ".angular", "coverage", ".git"} for part in path.parts):
                continue
            relative = path.relative_to(workspace).as_posix()
            lower = relative.lower()
            if "proxy" in lower and path.suffix in {".json", ".js", ".ts"}:
                proxy_files.append(relative)
            if any(token in lower for token in ("interceptor", "auth", "guard")) and path.suffix in {".ts", ".js"}:
                auth_files.append(relative)
            if path.suffix not in {".ts", ".js", ".json", ".env", ".html"}:
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for match in self._URL.finditer(content):
                api_roots.add(match.group(1))
            if re.search(r"interceptor|HttpClient|fetch\s*\(|axios|/api/", content, re.IGNORECASE):
                endpoint_indicators.append({"file": relative, "kind": "endpoint_or_interceptor_reference"})
            files.append(relative)
        snapshot = {"api_roots": sorted(api_roots), "proxy_files": sorted(set(proxy_files)), "endpoint_indicators": endpoint_indicators, "authentication_file_references": sorted(set(auth_files)), "inspected_files": files}
        return BaselineAnchor("backend_integration", snapshot, EvidenceConfidence.MACHINE_PROVEN, source="source scan")


def anchor_to_dict(anchor: BaselineAnchor) -> dict[str, Any]:
    value = asdict(anchor)
    value["confidence"] = anchor.confidence.value
    return value

