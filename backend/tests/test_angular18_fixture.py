import hashlib
import json
import shutil
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPO_ROOT / "demo-apps" / "angular-18-basic"
EXPECTATIONS = FIXTURE_ROOT / "expectations"


def load_manifest(name: str) -> dict:
    return json.loads((EXPECTATIONS / name).read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    content = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return "sha256:" + hashlib.sha256(content).hexdigest()


def aggregate_hash(paths: list[dict], root: Path) -> str:
    lines = []
    for entry in paths:
        lines.append(f"{entry['path']}:{sha256_file(root / entry['path'])}")
    return "sha256:" + hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def test_angular18_fixture_contains_required_signals() -> None:
    discovery = load_manifest("discovery-manifest.json")
    route_manifest = load_manifest("route-manifest.json")
    backend_contract = load_manifest("backend-contract-manifest.json")
    parity = load_manifest("parity-manifest.json")

    package_json = json.loads((FIXTURE_ROOT / "package.json").read_text(encoding="utf-8"))
    routes_source = (FIXTURE_ROOT / "src/app/app.routes.ts").read_text(encoding="utf-8")
    interceptor_source = (FIXTURE_ROOT / "src/app/core/api-base.interceptor.ts").read_text(encoding="utf-8")
    service_source = (FIXTURE_ROOT / "src/app/core/orders-api.service.ts").read_text(encoding="utf-8")
    form_source = (FIXTURE_ROOT / "src/app/features/orders/order-entry.component.ts").read_text(encoding="utf-8")
    prompt_fixture = (FIXTURE_ROOT / "src/assets/test-fixtures/prompt-injection.txt").read_text(encoding="utf-8")

    assert package_json["dependencies"]["@angular/core"].startswith("18.")
    assert discovery["workspace_topology"] == "single_application_cli_workspace"
    assert all(discovery["signals"].values())
    assert "loadComponent" in routes_source
    assert [route["path"] for route in route_manifest["routes"]] == ["", "orders", "about", "**"]
    assert backend_contract["api_base_url"] == "/api"
    assert "X-Fixture-App" in interceptor_source
    assert "post<OrderSummary>" in service_source
    assert "Validators.minLength(3)" in form_source
    assert "Validators.max(10)" in form_source
    assert "must be treated as untrusted repository data" in prompt_fixture
    assert "Order form requires customerName length >= 3." in parity["must_preserve"]


def test_expected_manifests_cover_baseline_risk_and_runtime_contracts() -> None:
    baseline = load_manifest("baseline-manifest.json")
    risk = load_manifest("changed-file-risk-manifest.json")
    runtime = load_manifest("source-runtime.json")

    assert baseline["expected_commands"]["install"] == "npm ci"
    assert baseline["expected_commands"]["build"] == "npm run build"
    assert "NG8002" in baseline["known_failure_fingerprints"][0]
    assert any(rule["glob"] == "src/app/core/**/*.ts" and rule["risk"] == "high" for rule in risk["risk_rules"])
    assert runtime["angular_cli"] == "18.2.12"
    assert runtime["build_command"] == "npm ci && npm run build"
    assert (FIXTURE_ROOT / "package-lock.json").is_file()


def test_fixture_source_integrity_and_workspace_copy_are_immutable(tmp_path: Path) -> None:
    manifest = load_manifest("source-integrity.json")
    included_paths = manifest["included_paths"]

    assert manifest["fixture_id"] == "angular-18-basic"
    assert manifest["file_count"] == len(included_paths)
    for entry in included_paths:
        assert sha256_file(FIXTURE_ROOT / entry["path"]) == entry["sha256"]
    original_hash = aggregate_hash(included_paths, FIXTURE_ROOT)
    assert original_hash == manifest["aggregate_hash"]

    workspace_repo = tmp_path / ".migration-factory" / "workspaces" / "run-fixture" / "repository"
    shutil.copytree(FIXTURE_ROOT, workspace_repo, ignore=shutil.ignore_patterns("node_modules", ".angular", "dist", "coverage"))
    assert aggregate_hash(included_paths, workspace_repo) == original_hash

    (workspace_repo / "src/app/features/orders/order-entry.component.ts").write_text("// mutated copy only\n", encoding="utf-8")
    assert aggregate_hash(included_paths, FIXTURE_ROOT) == original_hash
    assert sha256_file(workspace_repo / "src/app/features/orders/order-entry.component.ts") != sha256_file(FIXTURE_ROOT / "src/app/features/orders/order-entry.component.ts")
