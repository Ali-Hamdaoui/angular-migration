"""Deterministic structural parity-baseline builders for S2-F02-I01.

The builders inspect a run-owned immutable workspace.  They never execute
project code, claim functional parity, or expose source contents/secrets.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field


SCHEMA_VERSION = "parity-baseline-v1"
POLICY_VERSION = "s2-f02-sensitive-file-policy-v1"
_EXCLUDED_PARTS = {"node_modules", "dist", ".angular", "coverage", ".git"}
_TEXT_SUFFIXES = {".ts", ".tsx", ".js", ".mjs", ".json", ".html", ".scss", ".sass", ".css", ".env"}
_SECRET = re.compile(r"(token|api[_-]?key|authorization|password|secret)\s*[:=]\s*[^\s,;]+", re.IGNORECASE)


class ParityFinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    category: str
    file: str
    classification: str
    confidence: str = "machine_proven"
    indicators: tuple[str, ...] = ()
    manual_review_required: bool = False


class ParityEvidenceDraft(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    content: str
    checksum: str


class ParityBaselineResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    routes: tuple[dict[str, Any], ...] = ()
    backend_integration: dict[str, Any] = Field(default_factory=dict)
    sensitive_files: tuple[ParityFinding, ...] = ()
    ui_evidence: dict[str, Any] = Field(default_factory=dict)
    unknowns: tuple[str, ...] = ()
    evidence_drafts: tuple[ParityEvidenceDraft, ...] = ()


class SensitiveFilePolicy:
    """Classifies review-sensitive files without interpreting their behavior."""

    _RULES = (
        ("route", re.compile(r"(?:routes?|routing|redirect|loadChildren)", re.I)),
        ("auth", re.compile(r"(?:auth|token|cookie|guard|resolver)", re.I)),
        ("interceptor", re.compile(r"interceptor", re.I)),
        ("form", re.compile(r"(?:form|validator|FormGroup|FormControl)", re.I)),
        ("theme", re.compile(r"(?:theme|style|palette|typography)", re.I)),
        ("backend_integration", re.compile(r"(?:api|endpoint|proxy|HttpClient|axios|fetch)", re.I)),
        ("environment", re.compile(r"(?:environment|\.env|configuration)", re.I)),
    )

    def classify(self, workspace: Path) -> tuple[ParityFinding, ...]:
        findings: list[ParityFinding] = []
        for path in _source_files(workspace):
            relative = path.relative_to(workspace).as_posix()
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                findings.append(
                    ParityFinding(
                        category="unreadable",
                        file=relative,
                        classification="unknown",
                        confidence="unknown",
                        manual_review_required=True,
                    )
                )
                continue
            indicators = tuple(name for name, rule in self._RULES if rule.search(relative) or rule.search(content))
            if indicators:
                findings.append(
                    ParityFinding(
                        category="sensitive_file",
                        file=relative,
                        classification="behavior_sensitive_requires_review",
                        indicators=indicators,
                        manual_review_required=True,
                    )
                )
        return tuple(findings)


class RouteInventoryBuilder:
    _PROPERTY = {
        "path": re.compile(r"\bpath\s*:\s*(['\"])(.*?)\1"),
        "redirect_to": re.compile(r"\bredirectTo\s*:\s*(['\"])(.*?)\1"),
        "lazy_loader_indicator": re.compile(r"\bloadChildren\s*:\s*([^,}\n]+)"),
        "component_indicator": re.compile(r"\bcomponent\s*:\s*([A-Za-z_$][\w$]*)"),
        "guards": re.compile(r"\b(canActivate|canDeactivate|canLoad|canMatch)\s*:\s*\[([^\]]*)\]"),
        "resolver_indicator": re.compile(r"\bresolve\s*:\s*\{([^}]*)\}"),
    }

    def build(self, workspace: Path) -> tuple[tuple[dict[str, Any], ...], tuple[str, ...]]:
        routes: list[dict[str, Any]] = []
        unknowns: list[str] = []
        for path in _source_files(workspace, {".ts", ".tsx"}):
            relative = path.relative_to(workspace).as_posix()
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                unknowns.append(f"ROUTE_FILE_UNREADABLE:{relative}")
                continue
            for match in self._PROPERTY["path"].finditer(content):
                start, end = _route_window(content, match.start())
                window = content[start:end]
                entry: dict[str, Any] = {"path": match.group(2), "file": relative}
                for name, expression in self._PROPERTY.items():
                    if name == "path":
                        continue
                    found = expression.search(window)
                    if found:
                        entry[name] = (
                            found.group(2).strip() if name == "guards" else found.group(found.lastindex or 0).strip()
                        )
                routes.append(entry)
            if "provideRouter(" in content or "RouterModule.forRoot(" in content:
                if not self._PROPERTY["path"].search(content):
                    unknowns.append(f"DYNAMIC_OR_UNRESOLVED_ROUTES:{relative}")
        return tuple(sorted(routes, key=lambda item: (item["path"], item["file"]))), tuple(sorted(set(unknowns)))


class BackendContractSnapshotBuilder:
    _URL = re.compile(r"(?:apiUrl|apiRoot|baseUrl|baseURL|API_URL)\s*[:=]\s*[('\"]([^('\"]+)")
    _HTTP = re.compile(r"\.(get|post|put|patch|delete)\s*\(\s*(['\"])([^'\"]+)", re.I)

    def build(self, workspace: Path) -> tuple[dict[str, Any], tuple[str, ...]]:
        api_roots: set[str] = set()
        endpoints: list[dict[str, str]] = []
        auth_files: list[str] = []
        interceptor_files: list[str] = []
        environment_files: list[str] = []
        unknowns: list[str] = []
        for path in _source_files(workspace):
            relative = path.relative_to(workspace).as_posix()
            lower = relative.lower()
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                unknowns.append(f"BACKEND_FILE_UNREADABLE:{relative}")
                continue
            if any(token in lower for token in ("auth", "guard", "token", "cookie")):
                auth_files.append(relative)
            if "interceptor" in lower or "HttpInterceptor" in content:
                interceptor_files.append(relative)
            if "environment" in lower or path.suffix == ".env":
                environment_files.append(relative)
            for match in self._URL.finditer(content):
                api_roots.add(_safe_endpoint(match.group(1)))
            for match in self._HTTP.finditer(content):
                endpoints.append(
                    {"file": relative, "method": match.group(1).upper(), "endpoint": _safe_endpoint(match.group(3))}
                )
            if re.search(r"(?:HttpClient|fetch\s*\(|axios|XMLHttpRequest)", content) and not self._HTTP.search(content):
                unknowns.append(f"DYNAMIC_OR_UNRESOLVED_ENDPOINTS:{relative}")
        return (
            {
                "api_roots": sorted(api_roots),
                "endpoint_references": sorted(
                    endpoints, key=lambda item: (item["file"], item["method"], item["endpoint"])
                ),
                "authentication_file_references": sorted(set(auth_files)),
                "interceptor_file_references": sorted(set(interceptor_files)),
                "environment_file_references": sorted(set(environment_files)),
            },
            tuple(sorted(set(unknowns))),
        )


class ParityBaselineBuilder:
    def __init__(
        self,
        *,
        routes: RouteInventoryBuilder | None = None,
        backend: BackendContractSnapshotBuilder | None = None,
        sensitive_policy: SensitiveFilePolicy | None = None,
    ) -> None:
        self._routes = routes or RouteInventoryBuilder()
        self._backend = backend or BackendContractSnapshotBuilder()
        self._sensitive_policy = sensitive_policy or SensitiveFilePolicy()

    def build(self, workspace: Path) -> ParityBaselineResult:
        root = workspace.resolve(strict=True)
        if not root.is_dir():
            raise ValueError("PARITY_BASELINE_WORKSPACE_INVALID")
        routes, route_unknowns = self._routes.build(root)
        backend, backend_unknowns = self._backend.build(root)
        sensitive = self._sensitive_policy.classify(root)
        ui = _ui_evidence(root)
        unknowns = tuple(sorted(set((*route_unknowns, *backend_unknowns))))
        payloads = {
            "route_inventory.json": {"schema_version": SCHEMA_VERSION, "routes": routes, "unknowns": route_unknowns},
            "backend_integration_snapshot.json": {
                "schema_version": SCHEMA_VERSION,
                "snapshot": backend,
                "unknowns": backend_unknowns,
            },
            "sensitive_file_inventory.json": {
                "policy_version": POLICY_VERSION,
                "findings": [item.model_dump(mode="json") for item in sensitive],
            },
            "ui_theme_form_evidence.json": {"schema_version": SCHEMA_VERSION, "evidence": ui},
            "parity_manifest.json": {
                "schema_version": SCHEMA_VERSION,
                "policy_version": POLICY_VERSION,
                "proof_label": "NOT_PROVEN",
                "manual_validation_required": True,
                "unknowns": unknowns,
            },
        }
        drafts = tuple(_draft(name, value) for name, value in payloads.items())
        return ParityBaselineResult(
            routes=routes,
            backend_integration=backend,
            sensitive_files=sensitive,
            ui_evidence=ui,
            unknowns=unknowns,
            evidence_drafts=drafts,
        )


def _source_files(workspace: Path, suffixes: set[str] | None = None) -> Iterable[Path]:
    allowed = suffixes or _TEXT_SUFFIXES
    for path in sorted(workspace.rglob("*")):
        if (
            path.is_symlink()
            or not path.is_file()
            or path.suffix.lower() not in allowed
            or any(part in _EXCLUDED_PARTS for part in path.parts)
        ):
            continue
        yield path


def _route_window(content: str, offset: int) -> tuple[int, int]:
    return max(0, content.rfind("{", 0, offset)), min(len(content), content.find("}", offset) + 1 or len(content))


def _safe_endpoint(value: str) -> str:
    if value.startswith("/"):
        return value.split("?", 1)[0]
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "<redacted-endpoint>"
    if not parsed.scheme or not parsed.netloc:
        return "<redacted-endpoint>"
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))


def _ui_evidence(workspace: Path) -> dict[str, Any]:
    forms: list[str] = []
    themes: list[str] = []
    for path in _source_files(workspace):
        relative = path.relative_to(workspace).as_posix()
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if re.search(r"Form(Group|Control|Builder)|Validators", content):
            forms.append(relative)
        if path.suffix in {".scss", ".sass", ".css"} or re.search(r"theme|palette|typography", content, re.I):
            themes.append(relative)
    return {
        "form_file_references": sorted(set(forms)),
        "theme_file_references": sorted(set(themes)),
        "proof_label": "NOT_PROVEN",
        "manual_validation_required": True,
    }


def _draft(name: str, value: Any) -> ParityEvidenceDraft:
    content = json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2, default=list)
    redacted = _SECRET.sub("[REDACTED]", content)
    return ParityEvidenceDraft(
        name=name, content=redacted, checksum="sha256:" + hashlib.sha256(redacted.encode("utf-8")).hexdigest()
    )
