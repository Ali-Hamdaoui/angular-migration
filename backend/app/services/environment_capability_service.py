"""Build a redacted, actionable snapshot of local environment readiness."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Callable
from uuid import uuid4

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactType, CommandRequestDto, CommandStatus
from app.domain.system import (
    CorporateNetworkReadiness,
    EnvironmentCapabilityResult,
    EnvironmentCapabilitySnapshot,
    LocalStorageReadiness,
    RuntimeInventoryEntry,
)
from app.command_execution.worker import (
    CommandDefinition,
    CommandLogWriter,
    CommandPolicy,
    CommandRegistry,
    ExecutionWorker,
)
from app.core.config import Settings


class EnvironmentCapabilityService:
    """Probe runtimes through the command worker and inspect local storage/configuration."""

    policy_version = "environment-readiness-v1"
    runtime_names = ("node", "npm", "npx", "git", "python")
    _windows_executables = {
        "node": ("node.exe", "node"),
        "npm": ("npm.cmd", "npm"),
        "npx": ("npx.cmd", "npx"),
        "git": ("git.exe", "git"),
        "python": ("python.exe", "python", "py.exe", "py"),
    }

    def __init__(
        self,
        settings: Settings,
        worker: ExecutionWorker,
        artifact_store: LocalFilesystemArtifactStore,
        *,
        which: Callable[[str], str | None] = shutil.which,
        now_provider: Callable[[], datetime] | None = None,
        is_windows: bool | None = None,
    ) -> None:
        self._settings = settings
        self._worker = worker
        self._artifact_store = artifact_store
        self._which = which
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self._is_windows = os.name == "nt" if is_windows is None else is_windows

    def diagnose(self, idempotency_key: str = "environment-refresh") -> EnvironmentCapabilityResult:
        if not idempotency_key.strip():
            raise ValueError("idempotency_key must not be blank")

        captured_at = self._now_provider()
        snapshot_id = f"environment-{uuid4().hex[:12]}"
        self._artifact_store.ensure_run_layout(snapshot_id)

        runtimes = [self._probe_runtime(name, snapshot_id, idempotency_key, captured_at) for name in self.runtime_names]
        runtime_profiles = self._configured_runtime_profiles(snapshot_id, idempotency_key, captured_at)
        controlled_probes = self._controlled_probes(runtimes, snapshot_id, idempotency_key, captured_at)
        blockers: list[str] = []
        warnings: list[str] = []
        runtime_by_name = {runtime.name: runtime for runtime in runtimes}
        pair_names = ("node", "npm", "npx")
        pair_available = all(runtime_by_name[name].status == "available" for name in pair_names)
        # npm and npx are often shims or wrappers installed outside the Node
        # directory.  Each executable is proven by its own controlled probe;
        # directory equality is not evidence of incompatibility.
        paired = pair_available
        if not paired:
            blockers.append("RUNTIME_NODE_NPM_NPX_UNAVAILABLE")

        git_ready = runtime_by_name["git"].status == "available"
        python_ready = runtime_by_name["python"].status == "available"
        if not git_ready:
            blockers.append("GIT_UNAVAILABLE")
        if not python_ready:
            blockers.append("PYTHON_WORKER_UNAVAILABLE")

        storage = self._storage_readiness()
        if not storage.local_filesystem:
            blockers.append("LOCAL_STORAGE_REQUIRED")
        if not storage.writable:
            blockers.append("LOCAL_STORAGE_NOT_WRITABLE")
        if storage.free_bytes < self._settings.minimum_free_disk_bytes:
            blockers.append("DISK_SPACE_BELOW_THRESHOLD")

        network = self._network_readiness()
        if not network.strict_ssl:
            warnings.append("NPM_STRICT_SSL_DISABLED")
        if not network.registry_configured:
            warnings.append("NPM_REGISTRY_NOT_CONFIGURED")

        status = "blocked" if blockers else ("degraded" if warnings else "available")
        payload = {
            "snapshot_id": snapshot_id,
            "captured_at": captured_at,
            "policy_version": self.policy_version,
            "status": status,
            "runtimes": [runtime.model_dump(mode="json") for runtime in runtimes],
            "runtime_profiles": runtime_profiles,
            "node_npm_npx_paired": paired,
            "git_ready": git_ready,
            "python_ready": python_ready,
            "storage": storage.model_dump(mode="json"),
            "network": network.model_dump(mode="json"),
            "blockers": blockers,
            "warnings": warnings,
            "controlled_probes": controlled_probes,
        }
        snapshot = EnvironmentCapabilitySnapshot(**payload, checksum=self._checksum(payload))
        summary = self._artifact_store.write_text_artifact(
            snapshot_id,
            "global/00_setup/environment_capability_summary.json",
            json.dumps(snapshot.model_dump(mode="json"), indent=2, sort_keys=True),
            ArtifactType.JSON,
            created_by="environment-capability-service",
            created_at=captured_at,
            policy_version=self.policy_version,
        )
        inventory = self._artifact_store.write_text_artifact(
            snapshot_id,
            "global/00_setup/runtime_inventory.json",
            json.dumps(
                {"runtimes": [runtime.model_dump(mode="json") for runtime in runtimes], "runtime_profiles": runtime_profiles}, indent=2, sort_keys=True
            ),
            ArtifactType.JSON,
            created_by="environment-capability-service",
            created_at=captured_at,
            policy_version=self.policy_version,
        )
        return EnvironmentCapabilityResult(
            snapshot=snapshot,
            artifact={
                "summary": summary.ref.artifact_id,
                "runtime_inventory": inventory.ref.artifact_id,
            },
        )

    def _configured_runtime_profiles(self, snapshot_id: str, idempotency_key: str, now: datetime) -> list[dict[str, str]]:
        """Probe every explicitly approved runtime triplet through the structured worker."""
        profiles: list[dict[str, str]] = []
        run_root = self._artifact_store.ensure_run_layout(snapshot_id).resolve()
        for encoded in self._settings.approved_runtime_profiles:
            profile_id, node_raw, npm_raw, npx_raw = (part.strip() for part in encoded.split("|"))
            paths = {"node": Path(node_raw).resolve(), "npm": Path(npm_raw).resolve(), "npx": Path(npx_raw).resolve()}
            if not all(path.is_file() for path in paths.values()):
                continue
            definitions = tuple(
                CommandDefinition(f"configured-{profile_id}-{name}-version", str(path), ("--version",))
                for name, path in paths.items()
            )
            directories = list(dict.fromkeys(str(path.parent) for path in paths.values()))
            current_path = os.environ.get("PATH", "")
            policy = CommandPolicy(
                sandbox_root=run_root,
                registry=CommandRegistry(definitions=definitions),
                working_directory_aliases={"run_workspace": run_root},
                runtime_profiles=frozenset({profile_id}),
                network_profiles=frozenset({"none"}),
                environment_allowlist=("PATH",),
                environment_overrides={"PATH": os.pathsep.join([*directories, current_path])},
            )
            worker = ExecutionWorker(policy, CommandLogWriter(self._artifact_store))
            versions: dict[str, str] = {}
            for name, path in paths.items():
                execution = worker.run(CommandRequestDto(
                    command_id=f"configured-{profile_id}-{name}-version",
                    run_id=snapshot_id,
                    requester="environment-capability-service",
                    executable=str(path),
                    arguments=["--version"],
                    working_directory_alias="run_workspace",
                    runtime_profile_id=profile_id,
                    timeout_seconds=10,
                    network_profile="none",
                    idempotency_key=f"{idempotency_key}:{profile_id}:{name}",
                    requested_at=now,
                ))
                if execution.result.status is not CommandStatus.SUCCEEDED or execution.stdout_artifact is None:
                    versions = {}
                    break
                versions[name] = execution.stdout_artifact.content.splitlines()[0].strip().lstrip("v")
            if len(versions) == 3:
                profiles.append({
                    "profile_id": profile_id,
                    "node_executable": str(paths["node"]), "node_exact": versions["node"],
                    "npm_executable": str(paths["npm"]), "npm_exact": versions["npm"],
                    "npx_executable": str(paths["npx"]), "npx_exact": versions["npx"],
                })
        return profiles

    def _controlled_probes(self, runtimes, snapshot_id, idempotency_key, now):
        """Prove executable identity/configuration through the command authority."""
        by_name = {item.name: item for item in runtimes}
        probes = {}
        for name, command_id, arguments in (("node_exec_path", "node-exec-path", ["-p", "process.execPath"]), ("npm_registry", "npm-registry", ["config", "get", "registry"])):
            runtime = by_name["node" if name == "node_exec_path" else "npm"]
            if runtime.status != "available":
                probes[name] = {"status": "not_run", "value": None, "artifact_id": None}
                continue
            execution = self._worker.run(CommandRequestDto(command_id=command_id, run_id=snapshot_id, requester="environment-capability-service", executable=runtime.attempted_executable or runtime.executable or command_id.split("-")[0], arguments=arguments, working_directory_alias="run_workspace", runtime_profile_id="source-runtime-profile", timeout_seconds=10, network_profile="none", idempotency_key=f"{idempotency_key}:{command_id}", requested_at=now))
            value = execution.stdout_artifact.content.strip() if execution.stdout_artifact else None
            if name == "npm_registry" and value:
                from urllib.parse import urlsplit, urlunsplit
                parsed = urlsplit(value.splitlines()[0])
                value = urlunsplit((parsed.scheme, parsed.hostname or parsed.netloc, parsed.path, parsed.query, parsed.fragment)) if parsed.scheme else value.splitlines()[0]
            artifact_ref = getattr(execution.stdout_artifact, "ref", None)
            probes[name] = {"status": "passed" if execution.result.status is CommandStatus.SUCCEEDED else "failed", "value": value, "artifact_id": getattr(artifact_ref, "artifact_id", None)}
        return probes

    def _probe_runtime(
        self,
        name: str,
        snapshot_id: str,
        idempotency_key: str,
        now: datetime,
    ) -> RuntimeInventoryEntry:
        attempted_executable, executable = self._discover_executable(name)
        if not executable:
            return RuntimeInventoryEntry(
                name=name,
                attempted_executable=attempted_executable,
                status="missing",
                reason="The executable was not found in the backend process PATH.",
                remediation=self._missing_remediation(name),
            )

        request = CommandRequestDto(
            command_id=f"{name}-version",
            run_id=snapshot_id,
            requester="environment-capability-service",
            executable=attempted_executable,
            arguments=["--version"],
            working_directory_alias="run_workspace",
            runtime_profile_id="source-runtime-profile",
            timeout_seconds=10,
            network_profile="none",
            idempotency_key=f"{idempotency_key}:{name}",
            requested_at=now,
        )
        execution = self._worker.run(request)
        if execution.result.status is not CommandStatus.SUCCEEDED or execution.stdout_artifact is None:
            detail = self._execution_detail(execution)
            return RuntimeInventoryEntry(
                name=name,
                executable=executable,
                attempted_executable=attempted_executable,
                installation_root=str(Path(executable).resolve().parent),
                status="failed",
                reason=detail,
                remediation="Review the captured command stderr, then verify that this executable can run from the backend process account and PATH.",
            )
        version = execution.stdout_artifact.content.splitlines()[0].strip()
        return RuntimeInventoryEntry(
            name=name,
            executable=executable,
            attempted_executable=attempted_executable,
            version=version or None,
            installation_root=str(Path(executable).resolve().parent),
            status="available",
        )

    def _discover_executable(self, name: str) -> tuple[str, str | None]:
        candidates = self._windows_executables[name] if self._is_windows else (name,)
        for candidate in candidates:
            executable = self._which(candidate)
            if executable:
                return candidate, executable
        return candidates[0], None

    @staticmethod
    def _missing_remediation(name: str) -> str:
        if name == "python":
            return "Install Python or ensure python.exe (or the py launcher) is available in the backend process PATH."
        return f"Install {name} or add its executable directory to the backend process PATH, then restart the backend."

    @staticmethod
    def _execution_detail(execution) -> str:
        stderr = execution.stderr_artifact.content.strip() if execution.stderr_artifact else ""
        status = execution.result.status.value.lower()
        return f"The authoritative version probe {status}" + (f": {stderr}" if stderr else ".")

    def _storage_readiness(self) -> LocalStorageReadiness:
        artifact_root = self._settings.artifact_root.resolve()
        paths = [
            artifact_root,
            self._settings.workspace_root.resolve(),
            self._settings.snapshot_root.resolve(),
            self._database_path().parent,
        ]
        local = not any(str(path).startswith("\\\\") for path in paths)
        writable = all(self._is_writable(path) for path in paths)
        usage_path = next(
            (path if path.exists() else path.parent for path in paths if path.exists() or path.parent.exists()),
            Path.cwd(),
        )
        free_bytes = shutil.disk_usage(usage_path).free
        status = "blocked" if not local or not writable else "available"
        if free_bytes < self._settings.minimum_free_disk_bytes:
            status = "degraded"
        return LocalStorageReadiness(
            database_path=str(self._database_path()),
            artifact_root=str(artifact_root),
            writable=writable,
            local_filesystem=local,
            free_bytes=free_bytes,
            status=status,
        )

    def _network_readiness(self) -> CorporateNetworkReadiness:
        registry = os.getenv("NPM_CONFIG_REGISTRY") or os.getenv("npm_config_registry")
        proxy = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
        https_proxy = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
        strict_ssl = (os.getenv("NPM_CONFIG_STRICT_SSL") or "true").lower() not in {"0", "false", "no"}
        custom_ca = bool(os.getenv("NODE_EXTRA_CA_CERTS") or os.getenv("NPM_CONFIG_CAFILE"))
        return CorporateNetworkReadiness(
            registry_configured=bool(registry),
            proxy_configured=bool(proxy),
            https_proxy_configured=bool(https_proxy),
            strict_ssl=strict_ssl,
            custom_ca_configured=custom_ca,
        )

    def _database_path(self) -> Path:
        database_url = self._settings.database_url
        if database_url.startswith("sqlite:///"):
            return Path(database_url.removeprefix("sqlite:///")).resolve()
        return (self._settings.artifact_root / "migration-factory.db").resolve()

    @staticmethod
    def _is_writable(path: Path) -> bool:
        candidate = path if path.exists() else path.parent
        return candidate.exists() and os.access(candidate, os.W_OK)

    @staticmethod
    def _checksum(payload: dict) -> str:
        canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
