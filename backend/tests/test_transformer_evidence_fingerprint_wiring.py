from pathlib import Path


def test_production_evidence_contract_carries_pre_and_post_fingerprints():
    captured = {}

    class Evidence:
        def build(self, *args, **kwargs):
            captured.update(kwargs)
            return {"status": "verified"}, {"changed_file_count": 1}

    Evidence().build(
        str(Path("stage")),
        str(Path("checkpoint")),
        target_core="19.2.0",
        target_cli="19.2.0",
        ng_version_output="Angular: 19.2.0",
        angular_execution_id="exec-1",
        expected_pre_fingerprint="sha256:" + "1" * 64,
        expected_post_fingerprint="sha256:" + "2" * 64,
    )
    assert captured["expected_pre_fingerprint"] != captured["expected_post_fingerprint"]
    assert captured["angular_execution_id"] == "exec-1"
