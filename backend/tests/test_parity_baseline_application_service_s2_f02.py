import json
from pathlib import Path

import pytest

from app.services.parity_baseline_application_service import (
    ParityBaselineApplicationError,
    ParityBaselineApplicationService,
    ParityBaselineRequest,
)


class Runs:
    def __init__(self, workspace: Path, version: int = 4):
        self.workspace, self.version, self.records = workspace, version, {}

    def resolve_workspace(self, _run, artifacts):
        assert artifacts == ("baseline-artifact",)
        return self.workspace

    def state_version(self, _run):
        return self.version

    def get_idempotent(self, run, key):
        return self.records.get((run, key))

    def save_idempotent(self, run, key, checksum, result):
        self.records[(run, key)] = (checksum, result)


class Artifacts:
    def __init__(self, fail=False):
        self.fail = fail

    def register(self, _run, drafts):
        if self.fail:
            raise OSError("artifact store unavailable")
        return tuple(f"artifact-{draft.name}" for draft in drafts)


class Transitions:
    def __init__(self):
        self.calls = []

    def start(self, request):
        self.calls.append("start")
        return request.expected_state_version + 1

    def complete(self, request, artifacts):
        self.calls.append(("complete", artifacts))
        return request.expected_state_version + 2

    def block(self, request, code):
        self.calls.append(("block", code))
        return request.expected_state_version + 2


def request(**overrides):
    data = {
        "run_id": "run-1",
        "expected_state_version": 4,
        "idempotency_key": "parity-1",
        "prerequisite_artifact_ids": ("baseline-artifact",),
        "actor": "operator",
    }
    data.update(overrides)
    return ParityBaselineRequest(**data)


def workspace(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"@angular/core": "18.2.0"}}))
    (tmp_path / "angular.json").write_text(json.dumps({"projects": {"app": {"sourceRoot": "src"}}}))
    (tmp_path / "src" / "app.routes.ts").write_text(
        "export const routes = [{ path: 'admin', loadChildren: () => import('./admin.routes'), canActivate: [authGuard], resolve: { user: userResolver } }];"
    )
    (tmp_path / "src" / "api.service.ts").write_text(
        "const apiUrl = 'https://user:secret@example.test/api?token=nope'; http.get('/users');"
    )
    (tmp_path / "src" / "auth.interceptor.ts").write_text("export class AuthInterceptor {}")
    (tmp_path / "src" / "profile-form.ts").write_text("new FormGroup({});")
    (tmp_path / "src" / "theme.scss").write_text("$theme: blue;")
    return tmp_path


def test_parity_baseline_inspection_is_deterministic_redacted_and_requires_manual_parity_review(tmp_path):
    transitions = Transitions()
    result = ParityBaselineApplicationService(Runs(workspace(tmp_path)), Artifacts(), transitions).inspect(request())
    assert result.status == "completed"
    assert result.baseline and result.baseline.routes[0]["path"] == "admin"
    assert result.baseline.backend_integration["api_roots"] == ["https://example.test/api"]
    assert any("form" in item.indicators for item in result.baseline.sensitive_files)
    assert len(result.artifact_ids) == 5
    assert all(
        "secret" not in draft.content and "nope" not in draft.content for draft in result.baseline.evidence_drafts
    )
    assert transitions.calls[0] == "start" and transitions.calls[-1][0] == "complete"


def test_parity_discovers_typed_http_literals_and_excludes_control_files_from_behavior_review(tmp_path):
    root = workspace(tmp_path)
    (root / "src" / "user.service.ts").write_text(
        """
        export class UserService {
          list() { return this.http.get<User[]>('https://jsonplaceholder.typicode.com/users'); }
          create(user: User) { return this.http.post<User>('https://jsonplaceholder.typicode.com/users', user); }
        }
        """,
        encoding="utf-8",
    )
    (root / "src" / "app.config.ts").write_text(
        """
        import { provideHttpClient, withInterceptorsFromDi } from '@angular/common/http';
        export const appConfig = { providers: [provideHttpClient(withInterceptorsFromDi())] };
        """,
        encoding="utf-8",
    )
    (root / "src" / "user.service.spec.ts").write_text(
        """
        import { HttpClient, provideHttpClient } from '@angular/common/http';
        const httpClientSpy = { get: jest.fn(), post: jest.fn() };
        httpClientSpy.get.mockReturnValue([]);
        """,
        encoding="utf-8",
    )
    (root / "src" / "dynamic.service.ts").write_text(
        """
        export class DynamicService {
          list(url: string) { return this.http.get<User[]>(url); }
        }
        """,
        encoding="utf-8",
    )
    (root / ".vscode").mkdir()
    (root / ".vscode" / "settings.json").write_text(
        '{"authorization": "editor-only"}',
        encoding="utf-8",
    )
    (root / ".migration-factory").mkdir()
    (root / ".migration-factory" / "source-manifest.json").write_text(
        '{"files": [{"path": "src/auth.service.ts"}]}',
        encoding="utf-8",
    )

    result = ParityBaselineApplicationService(Runs(root), Artifacts(), Transitions()).inspect(request())

    endpoints = result.baseline.backend_integration["endpoint_references"]
    user_endpoints = [item for item in endpoints if item["file"] == "src/user.service.ts"]
    assert {(item["method"], item["endpoint"]) for item in user_endpoints} == {
        ("GET", "https://jsonplaceholder.typicode.com/users"),
        ("POST", "https://jsonplaceholder.typicode.com/users"),
    }
    assert "DYNAMIC_OR_UNRESOLVED_ENDPOINTS:src/user.service.ts" not in result.baseline.unknowns
    assert "DYNAMIC_OR_UNRESOLVED_ENDPOINTS:src/app.config.ts" not in result.baseline.unknowns
    assert "DYNAMIC_OR_UNRESOLVED_ENDPOINTS:src/user.service.spec.ts" not in result.baseline.unknowns
    assert "DYNAMIC_OR_UNRESOLVED_ENDPOINTS:src/dynamic.service.ts" in result.baseline.unknowns
    findings = {item.file: item for item in result.baseline.sensitive_files}
    assert findings[".vscode/settings.json"].classification == "excluded_non_behavioral"
    assert findings[".migration-factory/source-manifest.json"].classification == "excluded_non_behavioral"
    assert findings["src/auth.interceptor.ts"].classification == "behavior_sensitive_requires_review"


def test_parity_baseline_replays_identical_idempotency_and_rejects_changed_payload(tmp_path):
    service = ParityBaselineApplicationService(Runs(workspace(tmp_path)), Artifacts(), Transitions())
    assert not service.inspect(request()).idempotent_replay
    assert service.inspect(request()).idempotent_replay
    with pytest.raises(ParityBaselineApplicationError, match="different payload") as error:
        service.inspect(request(actor="another"))
    assert error.value.code == "IDEMPOTENCY_KEY_REUSED"


def test_parity_baseline_rejects_stale_state_before_side_effects(tmp_path):
    transitions = Transitions()
    with pytest.raises(ParityBaselineApplicationError) as error:
        ParityBaselineApplicationService(Runs(workspace(tmp_path), version=5), Artifacts(), transitions).inspect(
            request()
        )
    assert error.value.code == "STALE_STATE_VERSION"
    assert transitions.calls == []


def test_parity_baseline_preserves_safe_drafts_when_evidence_registration_fails(tmp_path):
    transitions = Transitions()
    result = ParityBaselineApplicationService(Runs(workspace(tmp_path)), Artifacts(fail=True), transitions).inspect(
        request()
    )
    assert result.status == "blocked"
    assert result.error_code == "PARITY_BASELINE_DEPENDENCY_FAILED"
    assert result.baseline and len(result.baseline.evidence_drafts) == 5
    assert transitions.calls == ["start", ("block", "PARITY_BASELINE_DEPENDENCY_FAILED")]
