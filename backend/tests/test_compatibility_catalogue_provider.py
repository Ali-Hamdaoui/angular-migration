from app.services.compatibility_catalogue_provider import CompatibilityCatalogueProvider


def test_provider_returns_versioned_catalogue_with_verified_checksum():
    catalogue = CompatibilityCatalogueProvider().load()
    assert catalogue.version == "catalog-v3"
    assert catalogue.checksum.startswith("sha256:")
    assert catalogue.entry_for("angular-18.x", "angular-19.x") is not None
    assert catalogue.entry_for("angular-11.x", "angular-12.x") is not None


def test_provider_covers_full_11_21_envelope():
    catalogue = CompatibilityCatalogueProvider().load()
    assert len(catalogue.entries) == 10
    for major in range(11, 21):
        assert catalogue.entry_for(f"angular-{major}.x", f"angular-{major + 1}.x") is not None


def test_provider_uses_stage_specific_node_runtime_constraints():
    catalogue = CompatibilityCatalogueProvider().load()

    assert catalogue.entry_for("angular-18.x", "angular-19.x").node_minimum == "18.19.1"
    assert catalogue.entry_for("angular-19.x", "angular-20.x").node_minimum == "20.19.0"
    assert catalogue.entry_for("angular-20.x", "angular-21.x").node_minimum == "20.19.0"
    # historical envelope entries carry official minimums
    assert catalogue.entry_for("angular-11.x", "angular-12.x").node_minimum == "12.14.0"
    assert catalogue.entry_for("angular-16.x", "angular-17.x").node_minimum == "18.13.0"


def test_provider_uses_stage_specific_typescript_ranges():
    catalogue = CompatibilityCatalogueProvider().load()
    entry = catalogue.entry_for("angular-12.x", "angular-13.x")
    assert entry.typescript_minimum == "4.4.3"
    assert entry.typescript_exclusive_maximum == "4.7.0"
    entry21 = catalogue.entry_for("angular-20.x", "angular-21.x")
    assert entry21.typescript_minimum == "5.9.0"
    assert entry21.typescript_exclusive_maximum == "6.0.0"


def test_current_catalogue_certifies_runtime_profiles_on_certified_transitions():
    entry = CompatibilityCatalogueProvider().load().entry_for("angular-18.x", "angular-19.x")
    assert entry.certification_status == "certified"
    assert entry.support_level == "historical_validated"
    assert entry.fixture_status == "passed"
    assert entry.validated_runtime_profiles == (("18.20.8", "10.8.2"),)


def test_seeded_official_entries_are_experimental_until_certification():
    entry = CompatibilityCatalogueProvider().load().entry_for("angular-11.x", "angular-12.x")
    assert entry.certification_status == "seeded_official"
    assert entry.support_level == "historical_experimental"
    assert entry.fixture_status == "incomplete"
    assert entry.certification_source == "angular.dev/reference/versions"


def test_catalog_v1_contract_remains_three_entries_without_runtime_profiles():
    catalogue = CompatibilityCatalogueProvider().load("catalog-v1")
    assert len(catalogue.entries) == 3
    assert catalogue.checksum.startswith("sha256:")
    entry = catalogue.entry_for("angular-18.x", "angular-19.x")
    assert entry.validated_runtime_profiles == ()
    assert entry.node_exact == "20.11.1"
    assert catalogue.entry_for("angular-11.x", "angular-12.x") is None
