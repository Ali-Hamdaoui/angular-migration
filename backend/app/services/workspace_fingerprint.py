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
- Stream encoding: per entry ``len(path_bytes).to_bytes(8, "big") + path_bytes
  + len(content_bytes).to_bytes(8, "big") + content_bytes`` fed into a single
  SHA-256 digest.  The length prefixes make the stream unambiguous
  (collision-resistant against path/content boundary ambiguity).
- Result format: ``sha256:<64 lowercase hex>``.

Sort contract (two entry points, two documented orders)
-------------------------------------------------------
- Tree profiles (``workspace_fingerprint_v1`` -> ``Profile.fingerprint``):
  entries sorted by ``(relative_posix_path.casefold(), relative_posix_path)``.
  This reproduces, deterministically on every platform, the ordering of the
  legacy implementations, which sorted ``Path`` objects directly
  (``sorted(item for item in root.rglob("*") if item.is_file())``); on Windows
  ``Path`` ordering compares normcase-lowercased full paths, so mixed-case
  trees ordered by the casefolded relative path.  The raw path is the
  deterministic tie-break (ties are impossible for distinct paths on any real
  filesystem).  Separators are normalized to forward slashes so the digest is
  independent of the host filesystem path separator.
- Manifest stream (``encode_fingerprint`` -> ``Profile.fingerprint_stream``):
  entries sorted by raw relative posix path code points.  This preserves the
  generic stream contract (``sorted(manifest.items())`` over
  already-posix-normalized keys) for callers that explicitly need raw order.
- Apply manifest (``encode_fingerprint_manifest`` ->
  ``Profile.fingerprint_manifest``): entries sorted by
  ``(relative_posix_path.casefold(), relative_posix_path)`` — the SAME
  ordering as the stage tree profile.  ``patch_apply_service`` hashes its
  apply-time workspace manifest with this function so the pre-check digest and
  the post-apply fingerprint recorded into the stage binding are
  byte-identical with ``StageWorkspaceBindingModel.workspace_fingerprint``
  (apples-to-apples comparison on mixed-case trees).

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
sort) and ``app.services.stage_preparation_primitives`` / ``ValidationRunner``
(identical length-prefixed stream encoding; implicit casefold ordering through
Windows ``Path`` sort).

- Stage-scope digests (stage bindings, checkpoints, repair-ledger pre/post
  fingerprints, sealed-output digests) are byte-identical with the digests
  persisted by legacy ``StageSandboxCopier.fingerprint``: same sort ordering,
  same stream encoding.
- Source-config digests (``ValidationRunner.source_fingerprint`` start/end
  evidence) are byte-identical with the legacy implementation: same sort
  ordering, same stream encoding, same exclusion set.
- Manifest-stream digests preserve raw code-point order through
  ``encode_fingerprint``/``fingerprint_stream``; the apply-time manifest
  (``encode_fingerprint_manifest``/``fingerprint_manifest``) uses the same
  casefold order as the stage tree profile so apply pre-checks and post-apply
  binding fingerprints compare apples-to-apples.
- Planning-scope digests are a deliberate versioned change: the legacy
  baseline fingerprint used a different encoding (path bytes + per-file
  content digest, no length prefixes).  Planning digests are re-created per
  run and no persisted expectation pins the old digest; the sort ordering is
  the same legacy-compatible casefold order used everywhere else.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

WORKSPACE_FINGERPRINT_VERSION = "workspace-fingerprint-v1"

WORKSPACE_FINGERPRINT_PLANNING_PROFILE_ID = f"{WORKSPACE_FINGERPRINT_VERSION}:planning"
WORKSPACE_FINGERPRINT_STAGE_PROFILE_ID = f"{WORKSPACE_FINGERPRINT_VERSION}:stage"
WORKSPACE_FINGERPRINT_SOURCE_CONFIG_PROFILE_ID = f"{WORKSPACE_FINGERPRINT_VERSION}:source-config"

PLANNING_VOLATILE_ROOTS = frozenset({"node_modules", ".angular", "dist", "coverage"})
STAGE_VOLATILE_NAMES = frozenset({"node_modules", ".angular", ".cache", "dist", "build", "logs", "reports", "tmp", ".pytest_cache"})


def _legacy_path_order_key(entry: tuple[str, bytes]) -> tuple[str, str]:
    """Sort key reproducing legacy Windows ``sorted(Path)`` ordering.

    Legacy code ordered files with ``sorted(item for item in root.rglob("*")
    if item.is_file())``.  On Windows, ``Path`` comparison uses
    ``os.path.normcase`` (lowercased) full paths, so mixed-case trees ordered
    by the casefolded relative path.  Returning the raw path as the second
    element keeps the order deterministic on every platform; ties cannot occur
    for distinct relative paths.
    """
    return (entry[0].casefold(), entry[0])


def _raw_path_order_key(entry: tuple[str, bytes]) -> str:
    return entry[0]


def _windows_path_order_key(entry: tuple[str, bytes]) -> tuple[str, ...]:
    """Reproduce pre-56893 ``sorted(WindowsPath)`` component ordering."""
    return tuple(part.casefold() for part in PurePosixPath(entry[0]).parts)


def _encode_stream(entries: Iterable[tuple[str, bytes]], *, sort_key: Callable[[tuple[str, bytes]], object]) -> str:
    digest = hashlib.sha256()
    for relative_path, content in sorted(entries, key=sort_key):
        relative = relative_path.encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return "sha256:" + digest.hexdigest()


def encode_fingerprint(entries: Iterable[tuple[str, bytes]]) -> str:
    """Encode a ``(relative_posix_path, content_bytes)`` stream into a canonical digest.

    Entries are ordered by raw relative posix path code points.  This is the
    generic manifest-stream contract (``sorted(manifest.items())`` over
    already-posix-normalized keys); callers that must compare against a
    persisted stage-tree digest should use ``encode_fingerprint_manifest``
    instead.
    """
    return _encode_stream(entries, sort_key=lambda entry: entry[0])


def encode_fingerprint_manifest(entries: Iterable[tuple[str, bytes]]) -> str:
    """Encode a ``(relative_posix_path, content_bytes)`` manifest into a canonical tree-order digest.

    Entries are ordered by ``(relative_posix_path.casefold(),
    relative_posix_path)`` — the same ordering as ``workspace_fingerprint_v1``
    and ``STAGE_FINGERPRINT_PROFILE.fingerprint``.  A manifest digest over a
    workspace tree is therefore byte-identical with the stage binding and
    checkpoint fingerprint persisted for the same tree.
    """
    return _encode_stream(entries, sort_key=_legacy_path_order_key)


def workspace_fingerprint_v1(
    root: Path,
    *,
    exclude: frozenset[str] = frozenset(),
    path_order: str = "casefold",
) -> str:
    """Fingerprint a workspace tree with the canonical v1 algorithm.

    Entries are ordered by ``(relative_posix_path.casefold(),
    relative_posix_path)`` by default.  ``path_order="raw"`` reproduces the
    raw POSIX implementation introduced by 56893cf; ``path_order="windows"``
    reproduces the earlier native ``sorted(WindowsPath)`` implementation.
    """
    root = Path(root).resolve(strict=True)
    entries: list[tuple[str, bytes]] = []
    for item in root.rglob("*"):
        if not item.is_file():
            continue
        relative = item.relative_to(root)
        if exclude and any(part in exclude for part in relative.parts):
            continue
        entries.append((relative.as_posix(), item.read_bytes()))
    sort_key = (
        _raw_path_order_key
        if path_order == "raw"
        else _windows_path_order_key
        if path_order == "windows"
        else _legacy_path_order_key
    )
    return _encode_stream(entries, sort_key=sort_key)


@dataclass(frozen=True)
class WorkspaceFingerprintProfile:
    """A named, versioned scope of the canonical workspace fingerprint."""

    version: str = WORKSPACE_FINGERPRINT_VERSION
    excluded_names: frozenset[str] = frozenset()
    profile_id: str | None = None
    path_order: str = "casefold"

    def fingerprint(self, root: Path) -> str:
        return workspace_fingerprint_v1(
            root, exclude=self.excluded_names, path_order=self.path_order
        )

    def fingerprint_stream(self, entries: Iterable[tuple[str, bytes]]) -> str:
        return encode_fingerprint(entries)

    def fingerprint_manifest(self, entries: Iterable[tuple[str, bytes]]) -> str:
        return encode_fingerprint_manifest(entries)


PLANNING_FINGERPRINT_PROFILE = WorkspaceFingerprintProfile(
    excluded_names=PLANNING_VOLATILE_ROOTS,
    profile_id=WORKSPACE_FINGERPRINT_PLANNING_PROFILE_ID,
)
STAGE_FINGERPRINT_PROFILE = WorkspaceFingerprintProfile(
    excluded_names=frozenset(),
    profile_id=WORKSPACE_FINGERPRINT_STAGE_PROFILE_ID,
)
SOURCE_CONFIG_FINGERPRINT_PROFILE = WorkspaceFingerprintProfile(
    excluded_names=STAGE_VOLATILE_NAMES,
    profile_id=WORKSPACE_FINGERPRINT_SOURCE_CONFIG_PROFILE_ID,
)
LEGACY_STAGE_RAW_ORDER_FINGERPRINT_PROFILE = WorkspaceFingerprintProfile(
    excluded_names=frozenset(),
    profile_id="legacy:workspace-fingerprint-v1:stage:raw-path-order",
    path_order="raw",
)
LEGACY_STAGE_WINDOWS_PATH_ORDER_FINGERPRINT_PROFILE = WorkspaceFingerprintProfile(
    excluded_names=frozenset(),
    profile_id="legacy:workspace-fingerprint-v1:stage:windows-path-order",
    path_order="windows",
)

#: Supported legacy fingerprint profiles, in deterministic identification order.
#:
#: A fingerprint persisted before profile identity existed is "legacy".  The
#: legacy stage-scope and source-config-scope implementations used the same
#: length-prefixed stream encoding as ``workspace-fingerprint-v1`` with their
#: documented exclusion sets, so their digests are byte-reproducible by the
#: corresponding current profile (see the module docstring).  The legacy
#: planning/baseline encoding is NOT reproducible and is therefore not a
#: supported candidate: a stored hash that matches no candidate fails closed.
#:
#: Identification is deterministic: candidates are evaluated in this exact
#: order, and a stored hash that matches more than one candidate is
#: ambiguous and fails closed.
SUPPORTED_LEGACY_FINGERPRINT_PROFILES: tuple[WorkspaceFingerprintProfile, ...] = (
    SOURCE_CONFIG_FINGERPRINT_PROFILE,
    STAGE_FINGERPRINT_PROFILE,
    LEGACY_STAGE_RAW_ORDER_FINGERPRINT_PROFILE,
    LEGACY_STAGE_WINDOWS_PATH_ORDER_FINGERPRINT_PROFILE,
)
