"""Canonical versioned workspace fingerprint profile (T01).

This module is the single authoritative implementation of workspace tree
fingerprints for planning and Transformer consumers.  Every other fingerprint
implementation in the codebase must resolve to this module (directly or through
a thin delegating wrapper that adds no behavior).

Profile identity
----------------
- ``WORKSPACE_FINGERPRINT_VERSION = "workspace-fingerprint-v1"`` is the versioned
  profile identity persisted alongside fingerprints (gate records, stage
  bindings, checkpoints).  Changing the algorithm is a deliberate, versioned
  change: bump this version and update every consumer and pinned expectation
  consistently.

Algorithm (workspace-fingerprint-v1)
------------------------------------
- File selection: every regular file under the root (``rglob``).  A file is
  excluded when ANY part of its relative posix path is a member of the
  profile's ``excluded_names`` set (volatile-root policy).  Files are read
  whole; content is hashed as bytes.
- Ordering: entries sorted by relative posix path (forward slashes, lower
  code-points first).  Sorting by posix path keeps the digest independent of
  the host filesystem path separator, which the legacy per-scope
  implementations were not.
- Stream encoding: per entry ``len(path_bytes).to_bytes(8, "big") + path_bytes
  + len(content_bytes).to_bytes(8, "big") + content_bytes`` fed into a single
  SHA-256 digest.  The length prefixes make the stream unambiguous
  (collision-resistant against path/content boundary ambiguity).
- Result format: ``sha256:<64 lowercase hex>``.

Scope policy
------------
The digest format and stream encoding are identical for every scope; scopes
differ only in the documented volatile-root exclusion set:

- Planning scope (``PLANNING_FINGERPRINT_PROFILE``): excludes
  ``PLANNING_VOLATILE_ROOTS = {node_modules, .angular, dist, coverage}`` at any
  depth.  Used by the baseline sandbox and G04/G05 workspace integrity
  verification.
- Stage scope (``STAGE_FINGERPRINT_PROFILE``): excludes nothing.  Stage
  sandboxes are copied with the stage exclusion policy applied, so the
  fingerprint covers every file present in the sandbox.
- Source-config scope (``SOURCE_CONFIG_FINGERPRINT_PROFILE``): excludes
  ``STAGE_VOLATILE_NAMES`` at any depth; used to prove read-only commands did
  not change source or configuration files.

Versioned change vs. legacy implementations
-------------------------------------------
This profile deliberately supersedes the legacy divergent implementations in
``app.workspaces.baseline`` (path + per-file content hash encoding, casefold
sort) and ``app.services.stage_preparation_primitives`` (identical stream
encoding; no length-prefix difference).  Persisted stage-binding and checkpoint
digests produced by the length-prefixed stream encoding remain unchanged under
the stage profile.  Planning-scope digests are a deliberate versioned change:
they are re-created per run and no persisted expectation pins the old digest.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

WORKSPACE_FINGERPRINT_VERSION = "workspace-fingerprint-v1"

PLANNING_VOLATILE_ROOTS = frozenset({"node_modules", ".angular", "dist", "coverage"})
STAGE_VOLATILE_NAMES = frozenset({"node_modules", ".angular", ".cache", "dist", "build", "logs", "reports", "tmp", ".pytest_cache"})


def encode_fingerprint(entries: Iterable[tuple[str, bytes]]) -> str:
    """Encode a ``(relative_posix_path, content_bytes)`` stream into a canonical digest."""
    digest = hashlib.sha256()
    for relative_path, content in sorted(entries, key=lambda item: item[0]):
        relative = relative_path.encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return "sha256:" + digest.hexdigest()


def workspace_fingerprint_v1(root: Path, *, exclude: frozenset[str] = frozenset()) -> str:
    """Fingerprint a workspace tree with the canonical v1 algorithm."""
    root = Path(root).resolve(strict=True)
    entries: list[tuple[str, bytes]] = []
    for item in root.rglob("*"):
        if not item.is_file():
            continue
        relative = item.relative_to(root)
        if exclude and any(part in exclude for part in relative.parts):
            continue
        entries.append((relative.as_posix(), item.read_bytes()))
    return encode_fingerprint(entries)


@dataclass(frozen=True)
class WorkspaceFingerprintProfile:
    """A named, versioned scope of the canonical workspace fingerprint."""

    version: str = WORKSPACE_FINGERPRINT_VERSION
    excluded_names: frozenset[str] = frozenset()

    def fingerprint(self, root: Path) -> str:
        return workspace_fingerprint_v1(root, exclude=self.excluded_names)

    def fingerprint_stream(self, entries: Iterable[tuple[str, bytes]]) -> str:
        return encode_fingerprint(entries)


PLANNING_FINGERPRINT_PROFILE = WorkspaceFingerprintProfile(excluded_names=PLANNING_VOLATILE_ROOTS)
STAGE_FINGERPRINT_PROFILE = WorkspaceFingerprintProfile(excluded_names=frozenset())
SOURCE_CONFIG_FINGERPRINT_PROFILE = WorkspaceFingerprintProfile(excluded_names=STAGE_VOLATILE_NAMES)
