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


def test_every_adjacent_transition_has_official_ranges_and_empirical_provenance():
    catalogue = CompatibilityCatalogueProvider().load()
    for major in range(11, 21):
        entry = catalogue.entry_for(f"angular-{major}.x", f"angular-{major + 1}.x")
        assert entry.source_node_ranges
        assert entry.target_node_ranges
        assert entry.typescript_minimum and entry.typescript_exclusive_maximum
        assert entry.rxjs_ranges
        assert entry.proven_runtime_profiles
        assert entry.proven_runtime_source == "dev-runtimes-real-e2e"


def test_empirical_profiles_do_not_promote_official_entry_to_certified():
    entry = CompatibilityCatalogueProvider().load().entry_for("angular-11.x", "angular-12.x")
    assert entry.proven_runtime_profiles
    assert entry.validated_runtime_profiles == ()
    assert entry.support_level == "historical_experimental"


def test_empirical_proof_binds_exact_source_target_and_cli_without_certifying():
    entry = CompatibilityCatalogueProvider().load().entry_for("angular-11.x", "angular-12.x")
    proof = entry.proven_runtime_evidence[0]

    assert proof.source_angular_exact == "11.0.4"
    assert proof.target_angular_exact == "12.2.17"
    assert proof.target_cli_exact == "12.2.18"
    assert proof.node_exact == "12.22.12"
    assert proof.npm_exact == "8.19.4"
    assert proof.proof_source == "dev-runtimes-real-e2e"
    assert proof.proof_status == "observed"
    assert entry.target_angular_exact == "12.0.0"
    assert entry.validated_runtime_profiles == ()


def test_certified_transition_keeps_official_target_separate_from_empirical_target():
    entry = CompatibilityCatalogueProvider().load().entry_for("angular-18.x", "angular-19.x")
    proof = entry.proven_runtime_evidence[0]

    assert entry.certification_status == "certified"
    assert entry.target_angular_exact == "19.0.0"
    assert proof.target_angular_exact == "19.2.25"
    assert entry.validated_runtime_profiles == (("18.20.8", "10.8.2"),)


def test_provider_uses_stage_specific_node_runtime_constraints():
    catalogue = CompatibilityCatalogueProvider().load()

    assert catalogue.entry_for("angular-18.x", "angular-19.x").node_minimum == "18.19.1"
    assert catalogue.entry_for("angular-19.x", "angular-20.x").node_minimum == "20.19.0"
    assert catalogue.entry_for("angular-20.x", "angular-21.x").node_minimum == "20.19.0"
    # historical envelope entries carry official minimums
    assert catalogue.entry_for("angular-11.x", "angular-12.x").node_minimum == "12.14.0"
    assert catalogue.entry_for("angular-16.x", "angular-17.x").node_minimum == "18.13.0"
    assert catalogue.entry_for("angular-11.x", "angular-12.x").source_node_ranges == ("^10.13.0", "^12.11.0")
    assert catalogue.entry_for("angular-16.x", "angular-17.x").target_node_ranges == ("^18.13.0", "^20.9.0")


def test_provider_uses_stage_specific_typescript_ranges():
    catalogue = CompatibilityCatalogueProvider().load()
    entry = catalogue.entry_for("angular-12.x", "angular-13.x")
    assert entry.typescript_minimum == "4.4.3"
    assert entry.typescript_exclusive_maximum == "4.7.0"
    entry21 = catalogue.entry_for("angular-20.x", "angular-21.x")
    assert entry21.typescript_minimum == "5.9.0"
    assert entry21.typescript_exclusive_maximum == "6.0.0"
    assert entry.rxjs_ranges == ("^6.5.3", "^7.4.0")


def test_current_catalogue_certifies_runtime_profiles_on_certified_transitions():
    entry = CompatibilityCatalogueProvider().load().entry_for("angular-18.x", "angular-19.x")
    assert entry.certification_status == "certified"
    assert entry.support_level == "historical_validated"
    assert entry.fixture_status == "passed"
    assert entry.validated_runtime_profiles == (("18.20.8", "10.8.2"),)
    assert entry.proven_runtime_profiles == (("22.23.1", "8.19.4"),)
    assert entry.proven_runtime_source == "dev-runtimes-real-e2e"


def test_seeded_official_entries_are_experimental_until_certification():
    entry = CompatibilityCatalogueProvider().load().entry_for("angular-11.x", "angular-12.x")
    assert entry.certification_status == "seeded_official"
    assert entry.support_level == "historical_experimental"
    assert entry.fixture_status == "incomplete"
    assert entry.certification_source == "angular.dev/reference/versions"
    assert entry.proven_runtime_profiles == (("12.22.12", "8.19.4"),)
    assert entry.proven_runtime_source == "dev-runtimes-real-e2e"


def test_catalogue_checksums_are_deterministic_across_loads():
    for version in ("catalog-v1", "catalog-v2", "catalog-v3"):
        first = CompatibilityCatalogueProvider().load(version)
        second = CompatibilityCatalogueProvider().load(version)
        assert first.checksum == second.checksum, version


def test_catalog_v1_contract_remains_three_entries_without_runtime_profiles():
    catalogue = CompatibilityCatalogueProvider().load("catalog-v1")
    assert len(catalogue.entries) == 3
    assert catalogue.checksum.startswith("sha256:")
    entry = catalogue.entry_for("angular-18.x", "angular-19.x")
    assert entry.validated_runtime_profiles == ()
    assert entry.node_exact == "20.11.1"
    assert catalogue.entry_for("angular-11.x", "angular-12.x") is None
