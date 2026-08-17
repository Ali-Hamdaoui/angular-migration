"""Angular stage knowledge contracts (V2 F17).

Per-major, per-stage knowledge drives migration stages: the expected transforms,
validation expectations, and dependency-change expectations for an adjacent-major
transition.  Entries are versioned and auditable.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


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
        "actions": ({"action": "run-official-angular-migrations", "package": "@angular/core"},),
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
