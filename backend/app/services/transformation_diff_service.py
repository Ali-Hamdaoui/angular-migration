from __future__ import annotations

import difflib
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from app.domain.transformation import (
    ChangedFileClassification,
    ChangedFileEntry,
    DiffSummary,
    SensitiveChangeReason,
    TransformationEvidenceMode,
)


@dataclass(frozen=True)
class TransformationDiffLimits:
    max_text_file_bytes: int = 10 * 1024 * 1024
    binary_sample_bytes: int = 8192
    max_files: int = 20_000
    max_total_scanned_bytes: int = 2 * 1024 * 1024 * 1024
    excluded_directory_names: frozenset[str] = frozenset(
        {".git", "node_modules", "dist", "build", "coverage", ".cache"}
    )
    excluded_relative_prefixes: tuple[str, ...] = (".angular/cache/",)


@dataclass(frozen=True)
class CanonicalDiffResult:
    summary: DiffSummary
    patch_bytes: bytes


class TransformationDiffError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class TransformationDiffService:
    def __init__(self, *, limits: TransformationDiffLimits | None = None) -> None:
        self.limits = limits or TransformationDiffLimits()

    def compute(self, source_root: Path, target_root: Path) -> CanonicalDiffResult:
        source_root = source_root.resolve(strict=True)
        target_root = target_root.resolve(strict=True)
        source_files = self._collect_files(source_root)
        target_files = self._collect_files(target_root)
        paths = sorted(set(source_files) | set(target_files), key=lambda p: p.as_posix())
        if len(paths) > self.limits.max_files:
            raise TransformationDiffError("TRANSFORMATION_FILE_LIMIT", "Transformation file-count limit exceeded.")

        entries: list[ChangedFileEntry] = []
        patch_parts: list[bytes] = []
        total_added = 0
        total_removed = 0
        scanned = 0

        for relative in paths:
            source = source_files.get(relative)
            target = target_files.get(relative)
            before_size = source.stat(follow_symlinks=False).st_size if source else None
            after_size = target.stat(follow_symlinks=False).st_size if target else None
            scanned += (before_size or 0) + (after_size or 0)
            if scanned > self.limits.max_total_scanned_bytes:
                raise TransformationDiffError("TRANSFORMATION_BYTE_LIMIT", "Transformation byte budget exceeded.")

            before_hash = self._stream_sha256(source) if source else None
            after_hash = self._stream_sha256(target) if target else None
            if source and target and before_hash == after_hash:
                continue

            change_type = "modified" if source and target else "deleted" if source else "added"
            sample_path = target or source
            assert sample_path is not None
            is_binary = self._is_binary(sample_path)
            oversized = (before_size or 0) > self.limits.max_text_file_bytes or (after_size or 0) > self.limits.max_text_file_bytes

            if is_binary or oversized:
                mode = (
                    TransformationEvidenceMode.BINARY_METADATA
                    if is_binary
                    else TransformationEvidenceMode.OVERSIZED_METADATA
                )
                marker = self._metadata_patch_marker(
                    relative.as_posix(),
                    change_type,
                    before_hash,
                    after_hash,
                    before_size,
                    after_size,
                    mode,
                )
                patch_parts.append(marker)
                classification, reason = self._classify_path(
                    relative.as_posix(), is_binary=is_binary, content_sample=None
                )
                entries.append(
                    ChangedFileEntry(
                        file_path=relative.as_posix(),
                        change_type=change_type,
                        classification=classification,
                        reason=reason,
                        is_binary=is_binary,
                        is_generated=self._is_generated(relative),
                        size_bytes=after_size if after_size is not None else before_size or 0,
                        before_sha256=before_hash,
                        after_sha256=after_hash,
                        before_size_bytes=before_size,
                        after_size_bytes=after_size,
                        evidence_mode=mode,
                        unsupported_reason=(
                            "binary content represented by metadata"
                            if is_binary
                            else "file exceeds text diff limit"
                        ),
                    )
                )
                continue

            before_bytes = self._normalized_text_bytes(source) if source else b""
            after_bytes = self._normalized_text_bytes(target) if target else b""
            if before_bytes == after_bytes:
                continue
            before_lines = before_bytes.decode("utf-8").splitlines(keepends=True)
            after_lines = after_bytes.decode("utf-8").splitlines(keepends=True)
            added, removed = self._count_line_operations(before_lines, after_lines)
            patch = self._unified_patch(relative.as_posix(), change_type, before_lines, after_lines)
            patch_parts.append(patch)
            total_added += added
            total_removed += removed
            content_sample = after_bytes[: self.limits.binary_sample_bytes] or before_bytes[: self.limits.binary_sample_bytes]
            classification, reason = self._classify_path(
                relative.as_posix(), is_binary=False, content_sample=content_sample
            )
            entries.append(
                ChangedFileEntry(
                    file_path=relative.as_posix(),
                    change_type=change_type,
                    classification=classification,
                    reason=reason,
                    lines_added=added,
                    lines_removed=removed,
                    is_binary=False,
                    is_generated=self._is_generated(relative),
                    size_bytes=after_size if after_size is not None else before_size or 0,
                    before_sha256=before_hash,
                    after_sha256=after_hash,
                    before_size_bytes=before_size,
                    after_size_bytes=after_size,
                    evidence_mode=TransformationEvidenceMode.FULL_DIFF,
                )
            )

        canonical_patch = b"".join(patch_parts)
        inventory_payload = [entry.model_dump(mode="json") for entry in entries]
        inventory_bytes = json.dumps(
            inventory_payload, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        counts: dict[str, int] = {}
        unsupported: list[str] = []
        for entry in entries:
            counts[entry.classification.value] = counts.get(entry.classification.value, 0) + 1
            if entry.evidence_mode != TransformationEvidenceMode.FULL_DIFF:
                unsupported.append(entry.file_path)

        summary = DiffSummary(
            total_files_changed=len(entries),
            total_lines_added=total_added,
            total_lines_removed=total_removed,
            files_by_classification=counts,
            changed_files=entries,
            diff_checksum="sha256:" + hashlib.sha256(canonical_patch).hexdigest(),
            inventory_checksum="sha256:" + hashlib.sha256(inventory_bytes).hexdigest(),
            truncated=False,
            unsupported_files=unsupported,
        )
        return CanonicalDiffResult(summary=summary, patch_bytes=canonical_patch)

    def fingerprint_tree(self, root: Path) -> str:
        root = root.resolve(strict=True)
        digest = hashlib.sha256()
        files = self._collect_files(root)
        for relative, path in sorted(files.items(), key=lambda item: item[0].as_posix()):
            digest.update(relative.as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(self._stream_sha256(path).encode("ascii"))
            digest.update(b"\0")
        return "sha256:" + digest.hexdigest()

    def _collect_files(self, root: Path) -> dict[PurePosixPath, Path]:
        result: dict[PurePosixPath, Path] = {}
        for path in root.rglob("*"):
            relative = PurePosixPath(path.relative_to(root).as_posix())
            if self._excluded(relative):
                continue
            if path.is_symlink():
                raise TransformationDiffError(
                    "TRANSFORMATION_SYMLINK", f"Symlink is not allowed: {relative.as_posix()}"
                )
            if path.is_file():
                result[relative] = path
        return result

    def _excluded(self, relative: PurePosixPath) -> bool:
        if any(part in self.limits.excluded_directory_names for part in relative.parts[:-1]):
            return True
        text = relative.as_posix()
        return any(text.startswith(prefix) for prefix in self.limits.excluded_relative_prefixes)

    @staticmethod
    def _stream_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(chunk_size):
                digest.update(chunk)
        return "sha256:" + digest.hexdigest()

    def _is_binary(self, path: Path) -> bool:
        with path.open("rb") as handle:
            sample = handle.read(self.limits.binary_sample_bytes)
        if b"\0" in sample:
            return True
        try:
            sample.decode("utf-8")
        except UnicodeDecodeError:
            return True
        return False

    @staticmethod
    def _normalized_text_bytes(path: Path) -> bytes:
        return path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")

    @staticmethod
    def _count_line_operations(before: list[str], after: list[str]) -> tuple[int, int]:
        added = 0
        removed = 0
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
            a=before, b=after, autojunk=False
        ).get_opcodes():
            if tag in {"replace", "delete"}:
                removed += i2 - i1
            if tag in {"replace", "insert"}:
                added += j2 - j1
        return added, removed

    @staticmethod
    def _unified_patch(path: str, change_type: str, before: list[str], after: list[str]) -> bytes:
        from_file = "/dev/null" if change_type == "added" else f"a/{path}"
        to_file = "/dev/null" if change_type == "deleted" else f"b/{path}"
        body = "".join(
            difflib.unified_diff(
                before,
                after,
                fromfile=from_file,
                tofile=to_file,
                n=3,
                lineterm="\n",
            )
        )
        return (f"diff --git a/{path} b/{path}\n" + body).encode("utf-8")

    @staticmethod
    def _metadata_patch_marker(
        path: str,
        change_type: str,
        before_hash: str | None,
        after_hash: str | None,
        before_size: int | None,
        after_size: int | None,
        mode: TransformationEvidenceMode,
    ) -> bytes:
        payload = {
            "path": path,
            "change_type": change_type,
            "mode": mode.value,
            "before_sha256": before_hash,
            "after_sha256": after_hash,
            "before_size_bytes": before_size,
            "after_size_bytes": after_size,
        }
        return (
            f"diff --git a/{path} b/{path}\n"
            f"AMFA-METADATA {json.dumps(payload, sort_keys=True, separators=(',', ':'))}\n"
        ).encode("utf-8")

    @staticmethod
    def _is_generated(relative: PurePosixPath) -> bool:
        text = relative.as_posix().lower()
        return text.startswith(("dist/", "build/", "coverage/", ".angular/"))

    def _classify_path(
        self, path: str, *, is_binary: bool, content_sample: bytes | None
    ) -> tuple[ChangedFileClassification, SensitiveChangeReason | None]:
        path_lower = path.lower()

        if is_binary:
            return ChangedFileClassification.BINARY, SensitiveChangeReason.BINARY_FILE

        if any(
            ci in path_lower
            for ci in [
                ".github/workflows/", ".github/actions/",
                ".gitlab-ci.yml", ".circleci/", "azure-pipelines",
                "jenkinsfile", "bitbucket-pipelines",
            ]
        ):
            return ChangedFileClassification.FORBIDDEN, None

        if any(
            cred in path_lower
            for cred in [
                ".env", ".envrc",
                "credentials", "secrets",
                ".pem", ".key", ".cert", "id_rsa",
                "service-account", "kubeconfig",
                ".netrc", ".pgpass",
            ]
        ):
            return ChangedFileClassification.FORBIDDEN, None

        if any(
            sec in path_lower
            for sec in [
                "security", ".htaccess", ".htpasswd",
                "allowed_signers", "snyk", "codeql",
            ]
        ):
            return ChangedFileClassification.FORBIDDEN, None

        if self._is_generated(PurePosixPath(path)):
            return ChangedFileClassification.GENERATED, SensitiveChangeReason.GENERATED_FILE

        if any(
            sens in path_lower
            for sens in ["auth", "security", "credential", "secret", "key", "token", "password"]
        ):
            reason = self._detect_content_reason(path, content_sample) or SensitiveChangeReason.AUTH_OR_API
            return ChangedFileClassification.SENSITIVE, reason

        if path_lower.endswith("package-lock.json") or path_lower.endswith("yarn.lock"):
            return ChangedFileClassification.MEDIUM_RISK, SensitiveChangeReason.PACKAGE_LOCK_CHANGE

        if path_lower.endswith((".ts", ".js", ".html", ".css", ".scss", ".json", ".py")):
            reason = self._detect_content_reason(path, content_sample)
            return ChangedFileClassification.LOW_RISK, reason

        reason = self._detect_content_reason(path, content_sample)
        return ChangedFileClassification.UNKNOWN, reason

    def _detect_content_reason(self, path: str, content_sample: bytes | None = None) -> SensitiveChangeReason | None:
        if content_sample is None:
            return None
        try:
            text = content_sample.decode("utf-8", errors="replace")
        except Exception:
            return None
        if any(p in text for p in ["HttpClient", "HttpHeaders", "HttpParams", "HttpInterceptor", "HttpHandler", "HttpEvent", "HttpRequest", "HttpResponse"]):
            return SensitiveChangeReason.AUTH_OR_API
        if any(p in text for p in ["RouterModule", "RouterLink", "RouterOutlet", "CanActivate", "CanActivateChild", "CanDeactivate", "CanLoad", "CanMatch", "Route", "Router"]):
            return SensitiveChangeReason.AUTH_OR_API
        if any(p in text for p in ["localStorage", "sessionStorage", "document.cookie", "eval(", "Function(", "setTimeout(", "innerHTML", "outerHTML"]):
            return SensitiveChangeReason.SECURITY_RELEVANT
        if path == "angular.json" or path.endswith("/angular.json") or any(p in text for p in ['"builder"', '"architect"', '"schematics"']):
            return SensitiveChangeReason.BUILD_SYSTEM_CHANGE
        if path.endswith((".json", ".conf", ".config", ".ini", ".cfg", ".yaml", ".yml")) and not path.endswith(("package.json", "package-lock.json", "yarn.lock")):
            return SensitiveChangeReason.CONFIGURATION_CHANGE
        if any(p in text for p in ["ngOnChanges", "ngDoCheck", "ngAfterViewInit", "ngAfterContentInit", "ngAfterViewChecked", "ngAfterContentChecked"]):
            return SensitiveChangeReason.BEHAVIOR_CHANGE
        if any(p in text for p in ["@deprecated", "TODO.*migrat", "FIXME.*angular"]):
            return SensitiveChangeReason.HIDDEN_MODERNIZATION
        if any(p in text for p in ["FormsModule", "ReactiveFormsModule", "FormBuilder", "FormGroup", "FormControl", "FormArray", "Validators."]):
            return SensitiveChangeReason.FORM_THEME_CHANGE
        if path.endswith((".scss", ".sass", ".css")) and any(p in text.lower() for p in ["theme", "palette", "typography", "--primary", "--secondary", "--accent"]):
            return SensitiveChangeReason.FORM_THEME_CHANGE
        return None
