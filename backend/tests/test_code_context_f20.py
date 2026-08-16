"""Tests for F20 code context intelligence."""

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.services.code_context_service import CodeContextError, CodeContextService

client = TestClient(app)


def _workspace(base: Path | None = None) -> Path:
    ws = (base or Path("/tmp")) / f"ws-{uuid4().hex[:8]}"
    ws.mkdir(parents=True)
    (ws / "app.component.ts").write_text(
        "import { Component } from '@angular/core';\n"
        "@Component({ selector: 'app-root', template: './app.component.html' })\n"
        "export class AppComponent {\n"
        "  title = 'app';\n"
        "  broken(): string {\n"
        "    return undefinedValue;\n"
        "  }\n"
        "}\n"
    )
    (ws / "app.component.html").write_text(
        "<h1>{{ title }}</h1>\n"
        "<app-child [input]='broken()'></app-child>\n"
    )
    return ws


def test_extract_ts_context_finds_symbol_block():
    service = CodeContextService()
    source = "export class AppComponent {\n  broken(): string {\n    return undefinedValue;\n  }\n}\n"
    units = service.extract_ts_context(source, "broken")
    assert len(units) == 1
    assert "return undefinedValue" in units[0].excerpt
    assert units[0].token_count > 0


def test_extract_template_context_finds_selector():
    service = CodeContextService()
    template = "<h1>{{ title }}</h1>\n<app-child [input]='broken()'></app-child>\n"
    units = service.extract_template_context(template, "app-child")
    assert len(units) == 1
    assert "app-child" in units[0].excerpt


def test_retrieve_context_bounded_budget():
    ws = _workspace()
    service = CodeContextService()
    bundle = service.retrieve_context(ws, ["broken"], ["app-child"], budget=200)
    assert bundle.total_tokens <= 200
    assert bundle.budget == 200
    assert bundle.checksum.startswith("sha256:")
    assert bundle.units


def test_retrieve_context_deterministic():
    ws = _workspace()
    service = CodeContextService()
    first = service.retrieve_context(ws, ["broken"], ["app-child"], budget=5000)
    second = service.retrieve_context(ws, ["broken"], ["app-child"], budget=5000)
    assert first.checksum == second.checksum


def test_retrieve_missing_workspace_raises(tmp_path: Path):
    service = CodeContextService()
    try:
        service.retrieve_context(tmp_path / "missing", ["broken"])
        assert False, "expected WORKSPACE_MISSING"
    except CodeContextError as exc:
        assert exc.code == "WORKSPACE_MISSING"


def test_api_retrieve(tmp_path: Path):
    ws = _workspace(tmp_path)
    response = client.post("/context/retrieve", json={"workspace_path": str(ws), "symbols": ["broken"], "template_selectors": ["app-child"], "budget": 2000})
    assert response.status_code == 200
    body = response.json()
    assert body["budget"] == 2000
    assert body["checksum"].startswith("sha256:")
    assert any(u["symbol"] == "broken" for u in body["units"])
