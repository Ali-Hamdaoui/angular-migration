from app.services.registry_snapshot_builder import RegistrySnapshotBuilder


def test_registry_snapshot_version_fallback_accepts_single_declared_range():
    assert RegistrySnapshotBuilder._single_version("~11.0.4") == "11.0.4"
    assert RegistrySnapshotBuilder._single_version(">=11.0.0 <12.0.0") is None
