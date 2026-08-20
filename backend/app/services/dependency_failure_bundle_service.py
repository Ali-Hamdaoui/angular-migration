"""Immutable full dependency-normalization evidence before reconstruction.

Frozen interface for P6: build_dependency_normalization_bundle(...) -> deterministic dict.
Full package-lock bytes remain immutable artifacts; only direct resolved versions
+ relevant peer info enter LLM context.  No workspace mutation performed.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from app.domain.transformation import FailureRoute

# ponytail: deterministic helpers, no filesystem mutation

SCHEMA_VERSION = "dependency-failure-bundle-v1"

_CHECKSUM_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SECRET_KEY_RE = re.compile(r"(token|auth|password|secret|_auth)", re.I)
# only relevant non-secret npm settings kept; secrets dropped deterministically
_RELEVANT_NPM_SETTINGS = frozenset(
    {
        "registry",
        "strict-peer-deps",
        "legacy-peer-deps",
        "engine-strict",
        "save-exact",
        "package-lock",
        "audit",
        "fund",
        "ignore-scripts",
        "save-prefix",
        "save-bundle",
        "save-optional",
        "save-dev",
        "save-prod",
        "package-manager",
        "node-version",
        "npm-version",
    }
)


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _checksum_of_package_json(value: Any) -> str:
    if value is None:
        return "missing"
    if isinstance(value, str):
        return _sha256_text(value)
    if isinstance(value, dict):
        # canonical json for determinism
        canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
        return _sha256_text(canonical)
    # fallback
    return _sha256_text(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str))


def _checksum_of_lock(value: Any) -> str:
    if value is None:
        return "missing"
    if isinstance(value, str):
        return _sha256_text(value)
    if isinstance(value, dict):
        canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
        return _sha256_text(canonical)
    if isinstance(value, bytes):
        return _sha256_bytes(value)
    return _sha256_text(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str))


def _extract_direct_resolved_versions(
    package_json: Any,
    package_lock: Any,
) -> dict[str, Any]:
    """Only direct deps' resolved versions, sorted, deterministic."""
    # normalize package_json to dict
    manifest: dict[str, Any] = {}
    if isinstance(package_json, dict):
        manifest = package_json
    elif isinstance(package_json, str):
        try:
            parsed = json.loads(package_json)
            if isinstance(parsed, dict):
                manifest = parsed
        except Exception:
            manifest = {}
    direct: set[str] = set()
    for section in ("dependencies", "devDependencies"):
        sec = manifest.get(section)
        if isinstance(sec, dict):
            direct.update(k for k in sec.keys() if isinstance(k, str))
    if not direct:
        return {}
    # lock packages map
    lock_dict: dict[str, Any] = {}
    if isinstance(package_lock, dict):
        lock_dict = package_lock
    elif isinstance(package_lock, str):
        try:
            parsed = json.loads(package_lock)
            if isinstance(parsed, dict):
                lock_dict = parsed
        except Exception:
            lock_dict = {}
    packages_map = lock_dict.get("packages") if isinstance(lock_dict.get("packages"), dict) else None
    legacy_deps = lock_dict.get("dependencies") if isinstance(lock_dict.get("dependencies"), dict) else None
    result: dict[str, Any] = {}
    for name in sorted(direct):
        version: Any = None
        if isinstance(packages_map, dict):
            entry = packages_map.get(f"node_modules/{name}")
            if isinstance(entry, dict):
                v = entry.get("version")
                if isinstance(v, str):
                    version = v
        if version is None and isinstance(legacy_deps, dict):
            entry = legacy_deps.get(name)
            if isinstance(entry, dict):
                v = entry.get("version")
                if isinstance(v, str):
                    version = v
        # keep None if missing, still deterministic
        result[name] = version
    return result


def _sanitize_npm_settings(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    kept: dict[str, Any] = {}
    for k, v in raw.items():
        if not isinstance(k, str):
            continue
        if _SECRET_KEY_RE.search(k):
            continue
        # keep only relevant keys to avoid secret leakage and noise
        # if whitelist defined, filter; else keep all non-secret
        # we keep relevant set plus any non-secret that is explicitly known safe
        # to satisfy "only relevant non-secret settings"
        # -> keep when key is in whitelist or looks like npm config without secret
        # minimal deterministic: keep if in whitelist
        if k not in _RELEVANT_NPM_SETTINGS:
            continue
        kept[k] = v
    return dict(sorted(kept.items()))


def _normalize_pre_update(
    pre_update: Any,
    pre_package_json: Any,
    pre_package_lock: Any,
) -> dict[str, Any]:
    if isinstance(pre_update, dict) and pre_update:
        pkg = pre_update.get("package_json")
        if pkg is None:
            pkg = pre_package_json
        pkg_checksum = pre_update.get("package_json_checksum")
        if not isinstance(pkg_checksum, str) or not _CHECKSUM_RE.match(pkg_checksum):
            pkg_checksum = _checksum_of_package_json(pkg)
        lock_checksum = pre_update.get("package_lock_checksum")
        if not isinstance(lock_checksum, str) or not _CHECKSUM_RE.match(lock_checksum):
            # try from raw lock
            if pre_package_lock is not None:
                lock_checksum = _checksum_of_lock(pre_package_lock)
            elif pre_update.get("package_lock") is not None:
                lock_checksum = _checksum_of_lock(pre_update.get("package_lock"))
            else:
                lock_checksum = "missing" if lock_checksum is None else lock_checksum
            if not isinstance(lock_checksum, str):
                lock_checksum = "missing"
        direct = pre_update.get("direct_resolved_versions")
        if not isinstance(direct, dict):
            direct = _extract_direct_resolved_versions(pkg, pre_package_lock if pre_package_lock is not None else pre_update.get("package_lock"))
        else:
            direct = dict(sorted(direct.items()))
        return {
            "package_json": pkg,
            "package_json_checksum": pkg_checksum,
            "package_lock_checksum": lock_checksum,
            "direct_resolved_versions": direct,
        }
    # synthesize from raw inputs
    pkg = pre_package_json
    # if pre_update contained package_json as string/dict but was empty dict case, fallback
    if isinstance(pre_update, dict) and "package_json" in pre_update:
        pkg = pre_update.get("package_json")
    return {
        "package_json": pkg,
        "package_json_checksum": _checksum_of_package_json(pkg),
        "package_lock_checksum": _checksum_of_lock(pre_package_lock),
        "direct_resolved_versions": _extract_direct_resolved_versions(pkg, pre_package_lock),
    }


def _normalize_post_failure(
    post_failure: Any,
    post_package_json: Any,
    post_package_lock: Any,
    pre_lock_checksum: str | None,
) -> dict[str, Any]:
    if isinstance(post_failure, dict) and post_failure:
        pkg = post_failure.get("package_json")
        if pkg is None:
            pkg = post_package_json
        pkg_checksum = post_failure.get("package_json_checksum")
        if not isinstance(pkg_checksum, str) or not _CHECKSUM_RE.match(pkg_checksum):
            pkg_checksum = _checksum_of_package_json(pkg)
        lock_checksum = post_failure.get("package_lock_checksum")
        if not isinstance(lock_checksum, str) or (not _CHECKSUM_RE.match(lock_checksum) and lock_checksum != "missing"):
            if post_package_lock is not None:
                lock_checksum = _checksum_of_lock(post_package_lock)
            elif post_failure.get("package_lock") is not None:
                lock_checksum = _checksum_of_lock(post_failure.get("package_lock"))
            else:
                lock_checksum = "missing" if lock_checksum is None else lock_checksum
        status = post_failure.get("package_lock_status")
        if not isinstance(status, str):
            if lock_checksum == "missing":
                status = "missing"
            elif pre_lock_checksum is not None and lock_checksum == pre_lock_checksum:
                status = "unchanged"
            else:
                status = "present"
        direct = post_failure.get("direct_resolved_versions")
        if not isinstance(direct, dict):
            direct = _extract_direct_resolved_versions(pkg, post_package_lock if post_package_lock is not None else post_failure.get("package_lock"))
        else:
            direct = dict(sorted(direct.items()))
        return {
            "package_json": pkg,
            "package_json_checksum": pkg_checksum,
            "package_lock_status": status,
            "package_lock_checksum": lock_checksum,
            "direct_resolved_versions": direct,
        }
    pkg = post_package_json
    if isinstance(post_failure, dict) and "package_json" in post_failure:
        pkg = post_failure.get("package_json")
    lock_checksum = _checksum_of_lock(post_package_lock)
    if lock_checksum == "missing":
        status = "missing"
    elif pre_lock_checksum is not None and lock_checksum == pre_lock_checksum:
        status = "unchanged"
    else:
        status = "present"
    return {
        "package_json": pkg,
        "package_json_checksum": _checksum_of_package_json(pkg),
        "package_lock_status": status,
        "package_lock_checksum": lock_checksum,
        "direct_resolved_versions": _extract_direct_resolved_versions(pkg, post_package_lock),
    }


def _normalize_command(command: Any, extra: dict[str, Any]) -> dict[str, Any]:
    if isinstance(command, dict) and command:
        cmd: dict[str, Any] = dict(command)
        # ensure deterministic artifact refs sorting
        # keep only expected keys, preserve others sorted
        result: dict[str, Any] = {}
        for k in ("command_id", "exit_code", "failure_code", "normalized_failure"):
            if k in cmd:
                result[k] = cmd[k]
            elif k in extra:
                result[k] = extra[k]
        # artifact refs: stdout/stderr etc - keep as refs, sorted
        for k in sorted(cmd.keys()):
            if k not in result:
                # artifact refs are dicts with artifact_id/checksum
                result[k] = cmd[k]
        # fill missing from extra
        if "command_id" not in result and "command_id" in extra:
            result["command_id"] = extra["command_id"]
        if "exit_code" not in result and "exit_code" in extra:
            result["exit_code"] = extra["exit_code"]
        if "failure_code" not in result and "failure_code" in extra:
            result["failure_code"] = extra["failure_code"]
        if "normalized_failure" not in result and "normalized_failure" in extra:
            result["normalized_failure"] = extra["normalized_failure"]
        # ensure artifact refs present as None if missing (deterministic)
        for ref_key in ("stdout_artifact_ref", "stderr_artifact_ref", "command_log_artifact_ref", "result_artifact_ref", "stdout_artifact_id", "stderr_artifact_id"):
            if ref_key not in result and ref_key in extra:
                result[ref_key] = extra[ref_key]
        return result
    # synthesize from extra
    return {
        "command_id": extra.get("command_id"),
        "exit_code": extra.get("exit_code"),
        "failure_code": extra.get("failure_code"),
        "normalized_failure": extra.get("normalized_failure"),
        "stdout_artifact_ref": extra.get("stdout_artifact_ref") or extra.get("stdout_artifact_id"),
        "stderr_artifact_ref": extra.get("stderr_artifact_ref") or extra.get("stderr_artifact_id"),
        "command_log_artifact_ref": extra.get("command_log_artifact_ref") or extra.get("command_log_artifact_id"),
        "result_artifact_ref": extra.get("result_artifact_ref") or extra.get("result_artifact_id"),
    }


def build_dependency_normalization_bundle(
    *,
    run_id: str | None = None,
    stage_id: str | None = None,
    execution_id: str | None = None,
    source_angular_exact: str | None = None,
    target_angular_exact: str | None = None,
    target_cli_exact: str | None = None,
    node_exact: str | None = None,
    npm_exact: str | None = None,
    pre_update: dict[str, Any] | None = None,
    post_failure: dict[str, Any] | None = None,
    command: dict[str, Any] | None = None,
    effective_npm_settings: dict[str, Any] | None = None,
    prior_normalization: dict[str, Any] | None = None,
    # raw convenience aliases for callers that pass package contents directly
    pre_package_json: Any = None,
    pre_package_lock: Any = None,
    post_package_json: Any = None,
    post_package_lock: Any = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build deterministic dependency-normalization bundle before reconstruction.

    All inputs are treated as immutable evidence; this function performs no
    filesystem mutation and returns a deterministic dict with sorted
    direct_resolved_versions and sanitized npm settings.  Full package-lock
    bytes are never embedded – only checksums and direct versions.
    """
    # allow run_id etc. to be passed via extra (e.g. P6 calling with dict spread)
    run_id = run_id if run_id is not None else extra.get("run_id")
    stage_id = stage_id if stage_id is not None else extra.get("stage_id")
    execution_id = execution_id if execution_id is not None else extra.get("execution_id")
    source_angular_exact = source_angular_exact if source_angular_exact is not None else extra.get("source_angular_exact")
    target_angular_exact = target_angular_exact if target_angular_exact is not None else extra.get("target_angular_exact")
    target_cli_exact = target_cli_exact if target_cli_exact is not None else extra.get("target_cli_exact")
    node_exact = node_exact if node_exact is not None else extra.get("node_exact")
    npm_exact = npm_exact if npm_exact is not None else extra.get("npm_exact")
    if pre_update is None and "pre_update" in extra:
        pre_update = extra.get("pre_update")
    if post_failure is None and "post_failure" in extra:
        post_failure = extra.get("post_failure")
    if command is None and "command" in extra:
        command = extra.get("command")
    if effective_npm_settings is None and "effective_npm_settings" in extra:
        effective_npm_settings = extra.get("effective_npm_settings")
    if prior_normalization is None and "prior_normalization" in extra:
        prior_normalization = extra.get("prior_normalization")
    # raw package contents may be in extra
    if pre_package_json is None:
        pre_package_json = extra.get("pre_package_json") or extra.get("pre_package_json_content")
    if pre_package_lock is None:
        pre_package_lock = extra.get("pre_package_lock") or extra.get("pre_package_lock_content") or extra.get("pre_lockfile")
    if post_package_json is None:
        post_package_json = extra.get("post_package_json") or extra.get("post_package_json_content")
    if post_package_lock is None:
        post_package_lock = extra.get("post_package_lock") or extra.get("post_package_lock_content") or extra.get("post_lockfile")

    # handle prior_normalization null vs summary deterministically
    prior: Any = prior_normalization
    if prior is None:
        # check extra for prior attempt marker
        if "prior_normalization" not in extra and "prior" not in extra:
            prior = None
    if isinstance(prior, dict):
        prior = dict(sorted(prior.items()))

    pre_norm = _normalize_pre_update(pre_update, pre_package_json, pre_package_lock)
    post_norm = _normalize_post_failure(post_failure, post_package_json, post_package_lock, pre_norm.get("package_lock_checksum"))
    cmd_norm = _normalize_command(command, extra)
    npm_settings_norm = _sanitize_npm_settings(effective_npm_settings if effective_npm_settings is not None else extra.get("effective_npm_settings") if isinstance(extra.get("effective_npm_settings"), dict) else extra.get("npm_settings"))

    # deterministic bundle: keys sorted for JSON determinism when dumped with sort_keys
    bundle: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "stage_id": stage_id,
        "execution_id": execution_id,
        "source_angular_exact": source_angular_exact,
        "target_angular_exact": target_angular_exact,
        "target_cli_exact": target_cli_exact,
        "node_exact": node_exact,
        "npm_exact": npm_exact,
        "pre_update": pre_norm,
        "post_failure": post_norm,
        "command": cmd_norm,
        "effective_npm_settings": npm_settings_norm,
        "prior_normalization": prior,
    }
    return bundle


# Re-export for discoverability
__all__ = ["SCHEMA_VERSION", "build_dependency_normalization_bundle"]
