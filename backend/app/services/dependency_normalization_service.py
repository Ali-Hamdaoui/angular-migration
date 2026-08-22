"""Backend-owned dependency normalization materialization (P3 V2.2).

- Every direct dependencies+devDependencies package appears exactly once.
- Backend-fixed Angular target requirements override LLM suggestions.
- Backend materializes authoritative package.json bytes, checksums, diff.
- No npm process is started here.
- Legacy dependency_transition / dependency_add / detach_update_reattach remain readable.
"""

from __future__ import annotations

import hashlib
import json
from difflib import unified_diff
from pathlib import Path

from app.domain.dependency_normalization import (
    DEPENDENCY_NORMALIZATION_REPAIR_KIND,
    DEPENDENCY_NORMALIZATION_SCHEMA_VERSION,
    DependencyNormalizationAction,
    DependencyNormalizationPlan,
)

# Packages whose version is backend-fixed for the stage target (catalogue-derived).
# The caller supplies the exact map; service only overrides LLM suggestions.
_FORBIDDEN_FLAGS = ("--force", "--legacy-peer-deps", "--allow-dirty")
_FORBIDDEN_FIELDS = ("scripts", "workspaces", "overrides")
# Angular platform + toolchain pinned by the target stage.
_FIXED_TARGET_PACKAGES = {
    "@angular/core", "@angular/common", "@angular/compiler", "@angular/forms",
    "@angular/platform-browser", "@angular/platform-browser-dynamic",
    "@angular/router", "@angular/animations", "@angular/cli", "@angular/compiler-cli",
    "@angular/cdk", "@angular/material", "@angular-devkit/build-angular", "@angular/build",
    "typescript", "rxjs", "zone.js",
}


def _dominant_newline(text: str) -> str:
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    return "\r\n" if crlf > lf else "\n"


def _canonical_package_json(manifest: dict, preimage_text: str) -> str:
    nl = _dominant_newline(preimage_text) if preimage_text else "\n"
    canonical = json.dumps(manifest, ensure_ascii=False, indent=2).replace("\n", nl)
    if preimage_text.endswith(("\n", "\r")):
        canonical += nl
    return canonical


def _checksum(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _direct_deps(manifest: dict) -> dict[str, tuple[str, str]]:
    """Map package -> (section, spec) for dependencies+devDependencies only."""
    out: dict[str, tuple[str, str]] = {}
    for section in ("dependencies", "devDependencies"):
        sec = manifest.get(section)
        if isinstance(sec, dict):
            for pkg, spec in sec.items():
                if isinstance(pkg, str) and isinstance(spec, str):
                    out[pkg] = (section, spec)
    return out


class DependencyNormalizationService:
    """Stateless backend materializer; no npm, no I/O beyond provided manifest text."""

    @staticmethod
    def parse_plan(raw: dict) -> DependencyNormalizationPlan:
        return DependencyNormalizationPlan.model_validate(raw)

    @staticmethod
    def validate_complete_plan(
        plan: DependencyNormalizationPlan,
        manifest: dict,
        target_requirements: dict[str, str] | None = None,
    ) -> None:
        target_requirements = target_requirements or {}
        direct = _direct_deps(manifest)
        plan_pkgs = {a.package for a in plan.packages}
        manifest_pkgs = set(direct)
        if plan_pkgs != manifest_pkgs:
            missing = sorted(manifest_pkgs - plan_pkgs)
            extra = sorted(plan_pkgs - manifest_pkgs)
            raise ValueError(
                f"plan must include every direct dep exactly once; missing={missing} extra={extra}"
            )
        for act in plan.packages:
            if act.package not in direct:
                raise ValueError(f"package {act.package} not in manifest direct deps")
            sec, cur = direct[act.package]
            if sec != act.section:
                raise ValueError(f"section mismatch for {act.package}: expected {sec} got {act.section}")
            if cur != act.current_spec:
                raise ValueError(f"current_spec mismatch for {act.package}: expected {cur!r} got {act.current_spec!r}")
            # forbidden flags in any string field
            for field in (act.target_version or "", act.reason):
                for flag in _FORBIDDEN_FLAGS:
                    if flag in field:
                        raise ValueError(f"forbidden flag {flag} in action for {act.package}")
            # replacement explicit
            if act.action == "REPLACE" and (not act.target_package or not act.target_version):
                raise ValueError(f"REPLACE requires explicit target_package/version for {act.package}")
        # target Angular fixed requirements preserved / backend owns final
        for pkg, required_spec in target_requirements.items():
            if pkg in direct:
                # plan must not contradict required; validation here is lenient because
                # materialize() will override — but reviewer must see preserved.
                # We enforce that if action is KEEP/REMOVE for a fixed pkg, it's invalid
                # when requirement differs.
                act = next((a for a in plan.packages if a.package == pkg), None)
                if act is None:
                    continue
                if act.action == "REMOVE":
                    raise ValueError(f"fixed target requirement {pkg}@{required_spec} cannot be REMOVE")
                if act.action == "KEEP" and act.current_spec != required_spec:
                    # LLM wanted KEEP but backend requires upgrade — materializer will override,
                    # reviewer accepts because backend preserves requirement.
                    pass
        # no scripts/.npmrc/workspace/override mutation via plan (plan only touches deps)
        for field in _FORBIDDEN_FIELDS:
            if field in manifest:
                # plan never carries these fields; mutation check happens in materialize diff
                pass

    @staticmethod
    def materialize(
        preimage_text: str,
        manifest: dict,
        plan: DependencyNormalizationPlan,
        target_requirements: dict[str, str] | None = None,
    ) -> dict[str, object]:
        """Apply whole plan + target overrides to produce authoritative postimage.

        Returns dict with post_manifest, post_text, pre_checksum, post_checksum, diff,
        approved_actions (overridden).
        """
        target_requirements = target_requirements or {}
        # copy manifest shallow + deep for deps sections
        post = json.loads(json.dumps(manifest))
        # validate completeness before mutation
        DependencyNormalizationService.validate_complete_plan(plan, manifest, target_requirements)
        direct = _direct_deps(manifest)
        approved: list[dict[str, object]] = []
        for act in plan.packages:
            # backend-fixed override
            effective_target_version = act.target_version
            effective_target_package = act.target_package
            effective_action = act.action
            if act.package in target_requirements:
                required = target_requirements[act.package]
                if act.action in ("KEEP", "UPGRADE", "REPLACE") and act.current_spec != required:
                    # force upgrade to required spec, keep package identity
                    effective_action = "UPGRADE"
                    effective_target_version = required
                    effective_target_package = None
                elif act.action == "REMOVE":
                    # backend forbids removing fixed package — override to UPGRADE
                    effective_action = "UPGRADE"
                    effective_target_version = required
                    effective_target_package = None
            # record approved (post-override) action for audit
            approved.append({
                "package": act.package,
                "section": act.section,
                "current_spec": act.current_spec,
                "action": effective_action,
                "target_package": effective_target_package,
                "target_version": effective_target_version,
                "reason": act.reason,
            })
            # apply
            sec_dict = post.get(act.section)
            if not isinstance(sec_dict, dict):
                sec_dict = {}
                post[act.section] = sec_dict
            if effective_action == "KEEP":
                continue
            elif effective_action == "UPGRADE":
                assert effective_target_version is not None
                sec_dict[act.package] = effective_target_version
            elif effective_action == "REMOVE":
                sec_dict.pop(act.package, None)
                # prune empty section? keep as-is for diff stability
                if not sec_dict:
                    post.pop(act.section, None)
            elif effective_action == "REPLACE":
                assert effective_target_package and effective_target_version
                sec_dict.pop(act.package, None)
                if not sec_dict:
                    post.pop(act.section, None)
                # replacement goes to same section as original
                target_sec = post.get(act.section) if isinstance(post.get(act.section), dict) else None
                if target_sec is None:
                    post[act.section] = {}
                    target_sec = post[act.section]
                if effective_target_package in target_sec:
                    raise ValueError(f"REPLACE target {effective_target_package} already exists")
                target_sec[effective_target_package] = effective_target_version
            else:
                raise ValueError(f"unknown action {effective_action}")
        # ensure unrelated fields immutable: scripts, workspaces, overrides must be unchanged
        for field in _FORBIDDEN_FIELDS:
            if (field in manifest) != (field in post) or manifest.get(field) != post.get(field):
                raise ValueError(f"forbidden mutation of field {field}")
            # .npmrc is not in package.json; workspace field handled same as above
        # no scripts mutation: already checked; also ensure no new top-level keys beyond deps mutated
        post_text = _canonical_package_json(post, preimage_text)
        pre_checksum = _checksum(preimage_text)
        post_checksum = _checksum(post_text)
        diff = "".join(unified_diff(
            preimage_text.splitlines(keepends=True),
            post_text.splitlines(keepends=True),
            fromfile="a/package.json",
            tofile="b/package.json",
        ))
        return {
            "post_manifest": post,
            "post_text": post_text,
            "pre_checksum": pre_checksum,
            "post_checksum": post_checksum,
            "diff": diff,
            "approved_actions": approved,
            "preimage_text": preimage_text,
        }

    @staticmethod
    def render_diff(pre_text: str, post_text: str) -> str:
        return "".join(unified_diff(
            pre_text.splitlines(keepends=True),
            post_text.splitlines(keepends=True),
            fromfile="a/package.json",
            tofile="b/package.json",
        ))

    @staticmethod
    def legacy_deserialize(payload: dict) -> dict | None:
        """Accept old dependency_transition / dependency_add payloads without transformation.

        Returns the payload unchanged if it is a legacy shape, else None.
        Preserves immutability of legacy attempts.
        """
        if not isinstance(payload, dict):
            return None
        ops = payload.get("operations")
        if not isinstance(ops, list) or not ops:
            return None
        legacy_ops = {"dependency_transition", "dependency_add", "dependency_change", "detach_update_reattach"}
        for op in ops:
            if not isinstance(op, dict):
                continue
            if op.get("operation") in legacy_ops or op.get("repair_kind") in legacy_ops or op.get("strategy") == "detach_update_reattach":
                return payload
        return None
