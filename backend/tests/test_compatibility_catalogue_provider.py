from app.services.compatibility_catalogue_provider import CompatibilityCatalogueProvider


def test_provider_returns_versioned_catalogue_with_verified_checksum():
    catalogue = CompatibilityCatalogueProvider().load()
    assert catalogue.version == "catalog-v1"
    assert catalogue.checksum.startswith("sha256:")
    assert catalogue.entry_for("angular-18.x", "angular-19.x") is not None


def test_provider_uses_stage_specific_node_runtime_constraints():
    catalogue = CompatibilityCatalogueProvider().load()

    assert catalogue.entry_for("angular-18.x", "angular-19.x").node_exact == "20.11.1"
    assert catalogue.entry_for("angular-19.x", "angular-20.x").node_exact == "20.19.0"
    assert catalogue.entry_for("angular-20.x", "angular-21.x").node_exact == "20.19.0"
