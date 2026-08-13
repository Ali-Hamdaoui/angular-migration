from app.services.compatibility_catalogue_provider import CompatibilityCatalogueProvider


def test_provider_returns_versioned_catalogue_with_verified_checksum():
    catalogue = CompatibilityCatalogueProvider().load()
    assert catalogue.version == "catalog-v3"
    assert catalogue.checksum.startswith("sha256:")
    assert catalogue.entry_for("angular-18.x", "angular-19.x") is not None


def test_provider_uses_stage_specific_node_runtime_constraints():
    catalogue = CompatibilityCatalogueProvider().load("catalog-v2")

    assert catalogue.entry_for("angular-18.x", "angular-19.x").node_exact == "20.11.1"
    assert catalogue.entry_for("angular-19.x", "angular-20.x").node_exact == "20.19.0"
    assert catalogue.entry_for("angular-20.x", "angular-21.x").node_exact == "20.19.0"


def test_current_catalogue_explicitly_validates_both_runtime_profiles():
    entry = CompatibilityCatalogueProvider().load("catalog-v2").entry_for("angular-18.x", "angular-19.x")

    assert entry.validated_runtime_profiles == (("20.11.1", "10.2.4"), ("22.23.1", "10.9.8"))


def test_catalog_v1_checksum_and_runtime_contract_remain_unchanged():
    catalogue = CompatibilityCatalogueProvider().load("catalog-v1")

    assert catalogue.checksum == "sha256:38e5546f8f22ecf5755ead93d8911ca96a4e5966f58a382348e1b48c98e1a75e"
    assert catalogue.entry_for("angular-18.x", "angular-19.x").validated_runtime_profiles == ()
