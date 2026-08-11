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
