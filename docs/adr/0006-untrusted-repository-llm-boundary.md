# ADR-0006: Untrusted Repository Content and LLM Boundary

## Status

Accepted for Sprint 0.

## Context

Repository files, comments, Markdown, package scripts, logs, diffs, and compiler
output can contain prompt injection, secrets, misleading instructions, or
hostile content.

## Decision

Repository content is untrusted data. The LLM Gateway is the only model access
path. It separates trusted platform instructions from untrusted source excerpts,
redacts secrets, limits context, records usage and cost, and validates model
responses against structured schemas before any proposal affects workflow.

Forbidden shortcuts:

- Sending whole repositories to the LLM by default.
- Allowing repository text to change policy, grant approval, or request tools.
- Storing raw secrets, credentials, cookies, private registry tokens, or hidden reasoning.
- Applying LLM-generated patches without backend validation and deterministic checks.
- Exposing Azure OpenAI credentials to agents or frontend code.

## Rationale

Prompt injection and secret leakage must be addressed before real migration
logic or real LLM calls exist. Treating all repository content as data keeps the
backend policy boundary intact.

## Consequences

LLM-related tests must include prompt-injection fixtures, redaction checks,
schema rejection, budget tracking, and artifact references rather than full raw
source dumps.
