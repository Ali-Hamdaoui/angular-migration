# Sprint 0 Threat Overview

This is not a full enterprise threat model. It records the Sprint 0 threats that
must be visible before real migration execution is added.

| Threat | Sprint 0 mitigation | Future gap |
|---|---|---|
| Path traversal | Normalize paths, use backend-owned roots, open artifacts by ID, reject escaping relative paths. | Add platform-specific path hardening and permission checks. |
| Command injection | Accept only structured commands with allowlisted executable and arguments; run with `shell=false`. | Add signed command registry and richer runtime isolation. |
| Prompt injection | Treat repository content as untrusted data; separate trusted policy from source excerpts in LLM context. | Add adversarial prompt regression suite and model promotion gates. |
| Secret leakage | Redact environment values, tokens, private registry credentials, Authorization headers, and production URLs before logs or LLM calls. | Add centralized secret scanner and artifact access controls. |
| Source mutation | Snapshot source, mutate only internal workspace, verify source manifest after workflow. | Add OS-level read-only mounts or container isolation. |
| Duplicate execution | Require idempotency keys, state versions, ordered events, and worker leases for accepted transitions. | Add distributed queue semantics before multi-worker operation. |
| Stale approval | Bind approvals to gate, actor, state version, artifact checksums, policy, scope, and expiry. | Add RBAC and separation-of-duties policy. |
| Artifact overwrite | Store immutable checksum-bound artifacts; reject path traversal and overwrite attempts. | Add remote artifact store immutability and retention policy. |

Non-negotiable review rule: a change that weakens one mitigation must update the
linked ADR, tests, and this overview before merge.
