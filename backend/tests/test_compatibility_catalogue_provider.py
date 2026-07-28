from app.services.compatibility_catalogue_provider import CompatibilityCatalogueProvider


def test_provider_returns_versioned_catalogue_with_verified_checksum():
    catalogue = CompatibilityCatalogueProvider().load()
    assert catalogue.version == "catalog-v1"
    assert catalogue.checksum.startswith("sha256:")
    assert catalogue.entry_for("angular-18.x", "angular-19.x") is not None
