"""Angular stage knowledge contracts (V2 F17 / V2.2 P1-2).

Per-major, per-stage knowledge drives migration stages: the expected transforms,
validation expectations, and dependency-change expectations for an adjacent-major
transition.  Entries are versioned and auditable.

V2.2 adds generic, versioned, checksum-bound deterministic repair rules whose
predicates consume normalized evidence and observed capabilities — never
executable Angular-major/package special cases.
"""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _payload_checksum(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


class StageKnowledgeEntry(_ImmutableModel):
    """One stage knowledge entry for an adjacent-major transition."""

    source_major: int = Field(ge=11, le=21)
    target_major: int = Field(ge=11, le=21)
    expected_transforms: tuple[str, ...] = Field(default_factory=tuple)
    validation_expectations: tuple[str, ...] = Field(default_factory=tuple)
    expected_dependency_changes: tuple[dict[str, str], ...] = Field(default_factory=tuple)
    dependency_rules: tuple[dict[str, str], ...] = Field(default_factory=tuple)
    migration_actions: tuple[dict[str, str], ...] = Field(default_factory=tuple)
    known_risks: tuple[str, ...] = Field(default_factory=tuple)
    version: int = Field(default=1, ge=1)
    notes: str = ""


def knowledge_entry_for(
    source_major: int, target_major: int, *, version: int = 1
) -> StageKnowledgeEntry:
    """Deterministic seeded stage knowledge for the 11-21 envelope (F17-02).

    The expected transforms mirror the official ng update migration suites for
    each adjacent major; validation expectations are the standard factory gates.
    """
    expected = {
        "transform": _transforms(source_major),
        "validate": ("build", "test"),
        "dependencies": _dependency_changes(source_major),
        "rules": _dependency_rules(source_major, target_major),
        "actions": (
            {"action": "run-official-angular-migrations", "package": "@angular/core"},
            {"action": "authorize-installed-migration-fallback", "package": "@angular/core"},
        ),
        "risks": _risks(source_major),
    }
    return StageKnowledgeEntry(
        source_major=source_major,
        target_major=target_major,
        expected_transforms=expected["transform"],
        validation_expectations=expected["validate"],
        expected_dependency_changes=expected["dependencies"],
        dependency_rules=expected["rules"],
        migration_actions=expected["actions"],
        known_risks=expected["risks"],
        version=version,
        notes="seeded from the official ng update migration guidance",
    )


class DeterministicRule(_ImmutableModel):
    """One versioned deterministic source-fix rule (V2.2 P1-2).

    Predicates consume normalized diagnostics and observed stage capabilities;
    the operation template renders only bounded P10 RepairIntent file
    operations against exact current preimages.  No rule may embed shell
    commands, runtime choices, or dependency/lock operations.
    """

    schema_version: str = "deterministic-rule-v1"
    rule_id: str = Field(min_length=1, max_length=128)
    version: int = Field(default=1, ge=1)
    active: bool = True
    diagnostic_predicates: tuple[dict[str, str], ...] = Field(min_length=1)
    stage_capability_predicates: tuple[dict[str, str], ...] = Field(default_factory=tuple)
    file_globs: tuple[str, ...] = Field(default_factory=tuple)
    required_preimage_sha256: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    operation_template: dict[str, str]
    expected_postcondition: str = Field(min_length=1)
    checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_and_bind(self) -> "DeterministicRule":
        allowed_operations = {"replace_text", "create_text_file", "delete_text_file"}
        if self.operation_template.get("operation_type") not in allowed_operations:
            raise ValueError("deterministic rules may only author bounded P10 file operations")
        if not self.operation_template.get("target_path"):
            raise ValueError("deterministic rules require a target path template")
        if self.checksum == _DRAFT_RULE_CHECKSUM:
            return self
        payload = self.model_dump(mode="json", exclude={"checksum"})
        expected = _payload_checksum(payload)
        if self.checksum != expected:
            raise ValueError("deterministic rule checksum does not bind its payload")
        return self

    def matches(
        self,
        *,
        normalized_diagnostics: tuple[dict[str, str], ...],
        observed_capabilities: dict[str, str],
    ) -> bool:
        for predicate in self.diagnostic_predicates:
            field_name = predicate.get("field")
            expected_value = predicate.get("value")
            if not any(item.get(field_name) == expected_value for item in normalized_diagnostics):
                return False
        for predicate in self.stage_capability_predicates:
            key = predicate.get("key")
            value = predicate.get("value", "present")
            if observed_capabilities.get(key) != value:
                return False
        return True

    @classmethod
    def create(cls, **fields) -> "DeterministicRule":
        draft = cls(**fields, checksum=_DRAFT_RULE_CHECKSUM)
        checksum = _payload_checksum(draft.model_dump(mode="json", exclude={"checksum"}))
        return draft.model_copy(update={"checksum": checksum})


_DRAFT_RULE_CHECKSUM = "sha256:" + "0" * 64


def evaluate_deterministic_rules(
    *,
    rules: tuple[DeterministicRule, ...],
    normalized_diagnostics: tuple[dict[str, str], ...],
    observed_capabilities: dict[str, str],
) -> tuple[str, "DeterministicRule | None"]:
    """Pure exact-match evaluation: zero matches, exactly one, or ambiguous.

    Multiple simultaneous matches fail closed; selection never falls back to
    ordering.
    """
    matched = [
        rule
        for rule in rules
        if rule.active and rule.matches(
            normalized_diagnostics=normalized_diagnostics,
            observed_capabilities=observed_capabilities,
        )
    ]
    if len(matched) > 1:
        return "AMBIGUOUS", None
    if not matched:
        return "NO_MATCH", None
    return "MATCH", matched[0]


def _transforms(source_major: int) -> tuple[str, ...]:
    # ng update auto-migrations that run during the transition.
    return tuple(
        filter(
            None,
            (
                "@angular/core:standalone" if source_major >= 19 else None,
                "@angular/core:control-flow" if source_major >= 17 else None,
                "@angular/core:inject" if source_major >= 16 else None,
                "@angular/cli:update-tsconfig-target",
            ),
        )
    )


def _dependency_changes(source_major: int) -> tuple[dict[str, str], ...]:
    changes = [{"package": "@angular/core", "action": "major-bump"}]
    if source_major == 12:
        # rxjs 6 -> 7 major bump happened at the Angular 13 transition.
        changes.append({"package": "rxjs", "action": "major-bump"})
    if source_major >= 19:
        changes.append({"package": "typescript", "action": "minor-bump"})
    return tuple(changes)


def _risks(source_major: int) -> tuple[str, ...]:
    risks = []
    if source_major <= 13:
        risks.append("legacy template syntax requires manual migration review")
    if source_major <= 15:
        risks.append("older ViewEngine-era decorators may require manual fixes")
    return tuple(risks)


def _dependency_rules(source_major: int, target_major: int) -> tuple[dict[str, str], ...]:
    """Capability predicates learned from historical Angular toolchains."""
    rules: list[dict[str, str]] = []
    if target_major >= 13:
        rules.extend(
            {
                "package": package,
                "action": "remove",
                "capability": f"package:{package}",
            }
            for package in ("tslint", "codelyzer")
        )
        rules.append({"package": "@angular-eslint", "action": "align", "capability": "package:angular-eslint"})
    if target_major == 12:
        rules.extend(
            {
                "package": package,
                "action": "align",
                "capability": f"package:{package}",
            }
            for package in ("codelyzer", "karma", "karma-jasmine-html-reporter")
        )
    rules.append({"package": "package-lock", "action": "use-legacy-parser", "capability": "lockfile_format:v1"})
    return tuple(rules)
