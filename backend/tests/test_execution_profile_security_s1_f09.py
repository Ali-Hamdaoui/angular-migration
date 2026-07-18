from datetime import UTC, datetime
from pathlib import Path
import shutil
import pytest
from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactType
from app.domain.execution_profile import RuntimeCandidate, RuntimeResolutionRequest, SourceRuntimeResolver

NOW=datetime(2026,7,15,tzinfo=UTC)
def candidate(**changes):
    values={"profile_id":"node-20","node_executable":r"C:\Tools\node20\node.exe","node_exact":"20.11.1","npm_executable":r"C:\Tools\node20\npm.cmd","npm_exact":"10.2.4","npx_executable":r"C:\Tools\node20\npx.cmd","npx_exact":"10.2.4","angular_cli_exact":"18.2.3"}; values.update(changes); return RuntimeCandidate(**values)
def request(c): return RuntimeResolutionRequest(source_angular_exact="18.2.3",source_typescript_exact="5.5.4",source_rxjs_exact="7.8.1",candidates=(c,),validated_at=NOW)

def test_mixed_node_npm_npx_installation_is_rejected():
    with pytest.raises(ValueError, match="one installation"):
        candidate(npm_executable=r"C:\OtherNode\npm.cmd")

def test_executable_replacement_invalidates_selected_profile():
    resolver=SourceRuntimeResolver(); profile=resolver.resolve(request(candidate())).selected_profile
    assert profile is not None
    changed=candidate(node_executable=r"C:\Tools\replacement\node.exe",npm_executable=r"C:\Tools\replacement\npm.cmd",npx_executable=r"C:\Tools\replacement\npx.cmd")
    assert resolver.is_stale(profile,changed,"angular-source-runtime-v1") is True

def test_policy_change_invalidates_selected_profile():
    resolver=SourceRuntimeResolver(); profile=resolver.resolve(request(candidate())).selected_profile
    assert profile is not None
    assert resolver.is_stale(profile,candidate(),"angular-source-runtime-v2") is True

def test_resolution_artifacts_are_read_only_by_id_and_checksum_bound():
    root = Path(__file__).resolve().parents[2] / ".s1f09-artifact-test"
    root.mkdir(parents=True, exist_ok=True)
    try:
        store=LocalFilesystemArtifactStore(root); stored=store.write_text_artifact("run-1","global/execution-profile/execution_profile.json",'{"checksum":"sha256:profile"}',ArtifactType.JSON,created_by="test",input_hashes={"request":"sha256:req"},policy_version="angular-source-runtime-v1")
        loaded=store.read_artifact_by_id(stored.ref.artifact_id)
        assert loaded.ref.checksum == stored.ref.checksum
        with pytest.raises(ValueError): store.read_artifact_by_id("artifact-../../secret")
    finally:
        shutil.rmtree(root, ignore_errors=True)

def test_runtime_profile_does_not_authorize_shell_or_arbitrary_execution():
    profile=SourceRuntimeResolver().resolve(request(candidate())).selected_profile
    assert profile is not None
    assert profile.angular_cli_execution == "npx"
    assert not hasattr(profile,"shell")
