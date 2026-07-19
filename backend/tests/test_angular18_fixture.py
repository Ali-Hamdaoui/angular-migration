"""Parametrized tests for all 7 Angular fixture generators."""

import json
from pathlib import Path

import pytest

from tests.fixture_generators.angular_fixture import (
    create_angular_fixture,
    create_angular_fixture_180x,
    create_cancellable_fixture,
    create_compiler_error_fixture,
    create_dependency_conflict_fixture,
    create_environment_blocker_fixture,
    create_passable_fixture,
)

# Generator tuples: (generator_func, name, fixture_type_label)
GENERATORS = [
    pytest.param(create_angular_fixture, "Customer Portal", "ANGULAR_182X", id="angular_182x"),
    pytest.param(create_angular_fixture_180x, "Angular18Workspace", "ANGULAR_180X", id="angular_180x"),
    pytest.param(create_passable_fixture, "PassableWorkspace", "PASSABLE", id="passable"),
    pytest.param(create_compiler_error_fixture, "CompilerErrorWorkspace", "COMPILER_ERROR", id="compiler_error"),
    pytest.param(create_dependency_conflict_fixture, "DepConflictWorkspace", "DEPENDENCY_CONFLICT", id="dependency_conflict"),
    pytest.param(create_environment_blocker_fixture, "EnvBlockerWorkspace", "ENVIRONMENT_BLOCKER", id="environment_blocker"),
    pytest.param(create_cancellable_fixture, "CancellableWorkspace", "CANCELLABLE", id="cancellable"),
]


class TestAllFixtureGenerators:
    """Verify every fixture generator produces a valid workspace tree."""

    @pytest.mark.parametrize("generator,name,_label", GENERATORS)
    def test_creates_directory_tree(self, generator, name: str, _label: str, tmp_path: Path) -> None:
        source = generator(tmp_path, name)
        assert source.is_dir()
        assert source.parent == tmp_path
        assert (source / "src" / "app").is_dir(), f"Missing src/app in {name}"
        assert (source / "package.json").is_file(), f"Missing package.json in {name}"
        assert (source / "angular.json").is_file(), f"Missing angular.json in {name}"
        assert (source / "tsconfig.json").is_file(), f"Missing tsconfig.json in {name}"

    @pytest.mark.parametrize("generator,name,_label", GENERATORS)
    def test_package_json_has_valid_json_and_name(self, generator, name: str, _label: str, tmp_path: Path) -> None:
        source = generator(tmp_path, name)
        pkg = json.loads((source / "package.json").read_text())
        assert pkg["name"] == name
        assert "dependencies" in pkg
        assert isinstance(pkg["dependencies"], dict)

    @pytest.mark.parametrize("generator,name,_label", GENERATORS)
    def test_angular_json_is_valid_json(self, generator, name: str, _label: str, tmp_path: Path) -> None:
        source = generator(tmp_path, name)
        cfg = json.loads((source / "angular.json").read_text())
        assert "projects" in cfg
        assert isinstance(cfg["projects"], dict)

    @pytest.mark.parametrize("generator,name,_label", GENERATORS)
    def test_tsconfig_json_is_valid_json(self, generator, name: str, _label: str, tmp_path: Path) -> None:
        source = generator(tmp_path, name)
        cfg = json.loads((source / "tsconfig.json").read_text())
        assert "compilerOptions" in cfg

    @pytest.mark.parametrize("generator,name,_label", GENERATORS)
    def test_deterministic(self, generator, name: str, _label: str, tmp_path: Path) -> None:
        """Same input produces the same output (byte-identical)."""
        source_a = generator(tmp_path / "run1", name)
        source_b = generator(tmp_path / "run2", name)
        files_a = sorted(source_a.rglob("*"))
        files_b = sorted(source_b.rglob("*"))
        assert len(files_a) == len(files_b), (
            f"Different file count: {len(files_a)} vs {len(files_b)}"
        )
        for fa, fb in zip(files_a, files_b):
            if fa.is_file() and fb.is_file():
                assert fa.read_bytes() == fb.read_bytes(), (
                    f"Content mismatch between {fa} and {fb}"
                )


class TestSourceFileContent:
    """Verify source files exist for generators that include them."""

    @pytest.mark.parametrize("generator,name,_label", [
        pytest.param(create_angular_fixture_180x, "Angular18Workspace", "ANGULAR_180X", id="angular_180x_src"),
        pytest.param(create_passable_fixture, "PassableWorkspace", "PASSABLE", id="passable_src"),
        pytest.param(create_compiler_error_fixture, "CompilerErrorWorkspace", "COMPILER_ERROR", id="compiler_error_src"),
        pytest.param(create_dependency_conflict_fixture, "DepConflictWorkspace", "DEPENDENCY_CONFLICT", id="dep_conflict_src"),
        pytest.param(create_environment_blocker_fixture, "EnvBlockerWorkspace", "ENVIRONMENT_BLOCKER", id="env_blocker_src"),
        pytest.param(create_cancellable_fixture, "CancellableWorkspace", "CANCELLABLE", id="cancellable_src"),
    ])
    def test_source_files_exist(self, generator, name: str, _label: str, tmp_path: Path) -> None:
        source = generator(tmp_path, name)
        assert (source / "src" / "app" / "main.ts").is_file(), f"Missing main.ts in {name}"
        # cancellable fixture intentionally omits app.module.ts (minimal blocking loop)
        if "cancellable" not in _label.lower():
            assert (source / "src" / "app" / "app.module.ts").is_file(), f"Missing app.module.ts in {name}"
        assert (source / "src" / "app" / "app.component.ts").is_file(), f"Missing app.component.ts in {name}"


class TestCompilerErrorFixture:
    def test_has_syntax_error_in_main_ts(self, tmp_path: Path) -> None:
        source = create_compiler_error_fixture(tmp_path)
        main_ts = (source / "src" / "app" / "main.ts").read_text()
        # Should have an intentional syntax error: missing closing parenthesis
        assert "// <-- intentional syntax error" in main_ts, (
            "Expected syntax error comment in main.ts"
        )
        # Verify the actual syntax error - missing closing paren on bootstrapModule
        code = main_ts.split("// <-- intentional")[0]
        # Count parentheses to find the imbalance
        opens = code.count("(")
        closes = code.count(")")
        assert opens > closes, (
            f"Expected unbalanced parentheses (opens={opens}, closes={closes})"
        )


class TestCancellableFixture:
    def test_has_blocking_loop_in_main_ts(self, tmp_path: Path) -> None:
        source = create_cancellable_fixture(tmp_path)
        main_ts = (source / "src" / "app" / "main.ts").read_text()
        assert "setTimeout" in main_ts, "Expected setTimeout loop in cancellable fixture"
        assert "blockingLoop" in main_ts, "Expected blockingLoop function"


class TestEnvironmentBlockerFixture:
    def test_has_precheck_script(self, tmp_path: Path) -> None:
        source = create_environment_blocker_fixture(tmp_path)
        assert (source / "scripts").is_dir(), "Missing scripts/ directory"
        assert (source / "scripts" / "precheck.js").is_file(), "Missing scripts/precheck.js"
        precheck = (source / "scripts" / "precheck.js").read_text()
        assert "process.exit(1)" in precheck, "Expected process.exit(1) in precheck script"

    def test_precheck_configured_in_package_json(self, tmp_path: Path) -> None:
        source = create_environment_blocker_fixture(tmp_path)
        pkg = json.loads((source / "package.json").read_text())
        assert "scripts" in pkg, "Missing scripts section"
        assert "precheck" in pkg["scripts"], "Missing precheck script"
        assert pkg["scripts"]["precheck"] == "node scripts/precheck.js"


class TestDependencyConflictFixture:
    def test_has_incompatible_dependency_versions(self, tmp_path: Path) -> None:
        source = create_dependency_conflict_fixture(tmp_path)
        pkg = json.loads((source / "package.json").read_text())
        deps = pkg["dependencies"]
        # Angular 19 with rxjs 6 is incompatible
        assert deps["@angular/core"] == "19.0.0"
        assert deps["rxjs"] == "6.6.7", "Should have rxjs 6.6.7 for incompatibility"


class TestSyntheticAngular182xFixture:
    def test_synthetic_angular_fixture_is_external(self, tmp_path: Path) -> None:
        source = create_angular_fixture(tmp_path, "Customer Portal")
        assert source.is_dir()
        assert source.parent == tmp_path
        assert (source / "package.json").is_file()
        assert (source / "angular.json").is_file()

    def test_default_dependencies(self, tmp_path: Path) -> None:
        source = create_angular_fixture(tmp_path, "Customer Portal")
        pkg = json.loads((source / "package.json").read_text())
        assert pkg["dependencies"]["@angular/core"] == "18.2.0"
        assert pkg["dependencies"]["@angular/cli"] == "18.2.12"
