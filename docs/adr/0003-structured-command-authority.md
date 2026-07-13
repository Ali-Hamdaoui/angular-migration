# ADR-0003: Structured Backend Command Authority

## Status

Accepted for Sprint 0.

## Context

Migration work eventually needs local tools such as Python, Node.js, npm, npx,
and Git. Raw shell strings and agent-direct execution create command-injection,
policy, path, and audit risks.

## Decision

Only the backend command execution boundary may start local processes. Callers
submit structured command requests with command ID, executable, arguments,
working-directory alias, runtime profile, timeout, network profile,
cancellation policy, idempotency key, and requester. The worker validates every
field against policy and runs with `shell=false`.

Forbidden shortcuts:

- Accepting raw shell commands from the UI, agents, LLM output, or repository files.
- Executing commands from arbitrary filesystem paths.
- Allowing `shell=true` in Sprint 0.
- Running install scripts or package downloads outside explicit future policy.
- Logging secrets in command records or artifacts.

## Rationale

Structured commands make execution reviewable, replayable, cancellable, and
safe to connect to state, approvals, artifacts, and runtime profiles.

## Consequences

Every command-capable feature must add tests for allowlist rejection,
working-directory policy, timeout behavior, output limits, and idempotent reuse.
