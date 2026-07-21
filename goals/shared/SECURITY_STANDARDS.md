# Security Standards

- Canonical path and symlink/junction containment; fail closed.
- External source read-only; mutation only in registered sandboxes.
- Command allowlist, structured argv, shell=false, cwd alias, environment allowlist, timeout, network profile, process-tree control.
- Never expose Azure/registry/proxy/cookie/auth secrets in child env, prompts, logs, artifacts, API, SSE, UI, screenshots, or docs.
- Repository/log/compiler/package content is untrusted data.
- LLM context is bounded, selected deterministically, sanitized, checksum-bound, and provenance-recorded.
- Patch paths, scope, checksum, current fingerprint, risk, and dry-run are validated before apply.
- Frontend cannot bypass backend gates or submit authoritative raw diffs.
- Add negative tests for command/argument injection, path traversal, forged IDs/checksums, stale state, payload reuse, oversized input, secret leakage, and malicious archive filenames.
