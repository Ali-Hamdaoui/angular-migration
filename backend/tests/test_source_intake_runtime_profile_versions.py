import json
from types import SimpleNamespace

from app.orchestration.source_intake import SourceIntakeDispatcher


def test_source_intake_uses_locked_angular_exact_for_runtime_profile(tmp_path):
    snapshot = tmp_path / "snapshot-id"
    snapshot.mkdir()
    (snapshot / "package.json").write_text(
        json.dumps(
            {
                "dependencies": {
                    "@angular/core": "^20.0.0",
                    "rxjs": "~7.8.0",
                },
                "devDependencies": {"typescript": "~5.8.3"},
            }
        ),
        encoding="utf-8",
    )
    (snapshot / "package-lock.json").write_text(
        json.dumps(
            {
                "packages": {
                    "node_modules/@angular/core": {"version": "20.3.27"},
                    "node_modules/typescript": {"version": "5.8.3"},
                }
            }
        ),
        encoding="utf-8",
    )
    run = SimpleNamespace(
        source_angular_version="^20.0.0",
        workspace_aliases={"SOURCE_SNAPSHOT": str(tmp_path)},
    )

    angular, typescript, rxjs = SourceIntakeDispatcher._source_versions(run)

    assert angular == "20.3.27"
    assert typescript == "~5.8.3"
    assert rxjs == "~7.8.0"


def test_source_intake_uses_legacy_lockfile_v1_exact_for_runtime_profile(tmp_path):
    snapshot = tmp_path / "snapshot-id"
    snapshot.mkdir()
    (snapshot / "package.json").write_text(
        json.dumps(
            {
                "dependencies": {
                    "@angular/core": "~11.1.1",
                    "rxjs": "~6.6.0",
                },
                "devDependencies": {"typescript": "~4.1.2"},
            }
        ),
        encoding="utf-8",
    )
    (snapshot / "package-lock.json").write_text(
        json.dumps(
            {
                "lockfileVersion": 1,
                "dependencies": {
                    "@angular/core": {"version": "11.1.2"},
                    "rxjs": {"version": "6.6.7"},
                    "typescript": {"version": "4.1.6"},
                },
            }
        ),
        encoding="utf-8",
    )
    run = SimpleNamespace(
        source_angular_version="~11.1.1",
        workspace_aliases={"SOURCE_SNAPSHOT": str(tmp_path)},
    )

    angular, typescript, rxjs = SourceIntakeDispatcher._source_versions(run)

    assert angular == "11.1.2"
    assert typescript == "~4.1.2"
    assert rxjs == "~6.6.0"


def test_source_intake_falls_back_to_declaration_when_lock_exact_unavailable(tmp_path):
    snapshot = tmp_path / "snapshot-id"
    snapshot.mkdir()
    (snapshot / "package.json").write_text(
        json.dumps({"dependencies": {"@angular/core": "~11.1.1"}}),
        encoding="utf-8",
    )
    (snapshot / "package-lock.json").write_text(
        json.dumps({"lockfileVersion": 1, "dependencies": {"rxjs": {"version": "6.6.7"}}}),
        encoding="utf-8",
    )
    run = SimpleNamespace(
        source_angular_version="~11.1.1",
        workspace_aliases={"SOURCE_SNAPSHOT": str(tmp_path)},
    )

    angular, _, _ = SourceIntakeDispatcher._source_versions(run)

    assert angular == "~11.1.1"


def test_source_intake_keeps_modern_lock_precedence_over_legacy(tmp_path):
    snapshot = tmp_path / "snapshot-id"
    snapshot.mkdir()
    (snapshot / "package.json").write_text(
        json.dumps({"dependencies": {"@angular/core": "~11.1.1"}}),
        encoding="utf-8",
    )
    (snapshot / "package-lock.json").write_text(
        json.dumps(
            {
                "lockfileVersion": 3,
                "packages": {"node_modules/@angular/core": {"version": "11.1.2"}},
                "dependencies": {"@angular/core": {"version": "11.1.3"}},
            }
        ),
        encoding="utf-8",
    )
    run = SimpleNamespace(
        source_angular_version="~11.1.1",
        workspace_aliases={"SOURCE_SNAPSHOT": str(tmp_path)},
    )

    angular, _, _ = SourceIntakeDispatcher._source_versions(run)

    assert angular == "11.1.2"
