from pathlib import Path
from tests.fixture_generators.angular_fixture import create_angular_fixture


def test_synthetic_angular_fixture_is_external(tmp_path: Path) -> None:
    source = create_angular_fixture(tmp_path, "Customer Portal")
    assert source.is_dir()
    assert source.parent == tmp_path
    assert (source / "package.json").is_file()
    assert (source / "angular.json").is_file()