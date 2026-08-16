"""Retrieval benchmark fixtures across majors (V2 F28-01).

Deterministic fixture workspaces over the 11 -> 21 set: each fixture is
generated from fixed templates (no timestamps, no randomness), so a
benchmark run is byte-reproducible.
"""

from __future__ import annotations

from pathlib import Path

from app.domain.retrieval_benchmark import BenchmarkFixtureKind, RetrievalBenchmarkCase


#: A deterministic, per-major fixture generator.  Each major gets a distinct
#: component/service/module/template so the fixture set spans 11 -> 21.
def _fixture_files(source_major: int) -> dict[str, str]:
    next_major = source_major + 1
    component_symbol = f"App{source_major}Component"
    service_symbol = f"Data{source_major}Service"
    selector = f"app-{source_major}"
    return {
        "app.component.ts": (
            "import { Component } from '@angular/core';\n"
            f"import {{ Data{source_major}Service }} from './data.service';\n"
            f"@Component({{ selector: '{selector}', template: './app.component.html' }})\n"
            f"export class {component_symbol} {{\n"
            "  title = 'app';\n"
            f"  constructor(private data: Data{source_major}Service) {{}}\n"
            f"  broken(): string {{\n"
            "    return undefinedValue;\n"
            "  }\n"
            "}\n"
        ),
        "app.component.html": (
            "<h1>{{ title }}</h1>\n"
            f"<{selector} [input]='broken()'></{selector}>\n"
        ),
        "data.service.ts": (
            "import { Injectable } from '@angular/core';\n"
            "@Injectable({ providedIn: 'root' })\n"
            f"export class {service_symbol} {{\n"
            f"  fetch(): Promise<string> {{\n"
            f"    return Promise.resolve('angular-{source_major}.x');\n"
            "  }\n"
            "}\n"
        ),
        "app.module.ts": (
            "import { NgModule } from '@angular/core';\n"
            f"import {{ {component_symbol} }} from './app.component';\n"
            f"@NgModule({{ declarations: [{component_symbol}] }})\n"
            "export class AppModule {}\n"
        ),
    }


def build_fixture_workspace(root: Path, case: RetrievalBenchmarkCase) -> Path:
    """Materialize one deterministic fixture workspace on disk."""
    workspace = root / case.case_id
    workspace.mkdir(parents=True, exist_ok=True)
    files = _fixture_files(case.source_major)
    for relative, content in files.items():
        (workspace / relative).write_text(content, encoding="utf-8")
    return workspace


def benchmark_fixture_set() -> list[RetrievalBenchmarkCase]:
    """The full deterministic 11 -> 21 fixture set (F28-01)."""
    cases: list[RetrievalBenchmarkCase] = []
    for source_major in range(11, 21):
        component_symbol = f"App{source_major}Component"
        service_symbol = f"Data{source_major}Service"
        selector = f"app-{source_major}"
        cases.append(
            RetrievalBenchmarkCase(
                case_id=f"fixture-{source_major}-component",
                fixture_kind=BenchmarkFixtureKind.COMPONENT,
                source_major=source_major,
                symbols=(component_symbol, service_symbol, "broken"),
                template_selectors=(selector,),
                budget=6000,
                relevant_files=("app.component.ts", "app.component.html", "data.service.ts", "app.module.ts"),
            )
        )
        cases.append(
            RetrievalBenchmarkCase(
                case_id=f"fixture-{source_major}-service",
                fixture_kind=BenchmarkFixtureKind.SERVICE,
                source_major=source_major,
                symbols=(service_symbol, "fetch"),
                budget=6000,
                relevant_files=("data.service.ts",),
            )
        )
        cases.append(
            RetrievalBenchmarkCase(
                case_id=f"fixture-{source_major}-module",
                fixture_kind=BenchmarkFixtureKind.MODULE,
                source_major=source_major,
                symbols=(component_symbol, "AppModule"),
                budget=6000,
                relevant_files=("app.module.ts", "app.component.ts"),
            )
        )
    return cases
