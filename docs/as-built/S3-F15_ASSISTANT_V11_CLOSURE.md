# S3-F15 Assistant V1.1 closure

## Approved scope

The MVP is a single trusted operator using a configured technical actor, with no login and no multi-user security claim. OIDC, OAuth, JWT, Entra ID, and session management remain explicit future non-goals. This document does not declare Angular migration success.

## R10 defect and correction

The repeated real-Azure failures were a production contract defect. The backend selected `intent` and `capability_key`, but the provider schema and policy did not bind those selected values. The provider could therefore return another structurally valid category. Evidence selection also constrained excerpt membership incompletely and did not bind the provider citation identity to the selected source map. A status request could additionally receive evidence context when evidence was not requested.

The correction is narrow and fail-closed:

- dynamic strict response contracts bind selected `intent` and `capability_key` to one-value literals;
- capability policy explicitly states selected dispatch, required projection fields, evidence rules, proof labels, next-step behavior, and unknown handling;
- composite blocker-plus-next-action variations deterministically select the existing `failure_explanation` capability;
- evidence schemas bind the provider citation subset to selected excerpt/source identities, while backend validation remains authoritative;
- evidence retrieval is limited to `evidence_question` requests;
- provider citations are persisted and returned as the exact validated subset; normalization does not fabricate, replace, or attach citations.

Strict required fields, closed enums, `additionalProperties=false`, schema versioning, semantic validation, citation membership, identity, and proof-label validation remain enabled.

## Acceptance

Real Azure first attempts passed for workflow status, blocker-plus-next-action follow-up, and approved evidence. The formerly failing follow-up and evidence scenarios each passed twice consecutively on fresh attempts with separate request/idempotency identifiers and no user Retry. Usage and lifecycle metadata persisted. A deliberate invalid-response proof remained fail-closed.

The real mounted FastAPI/Next UI passed status, same-conversation follow-up, hard reload restoration without duplicates, and evidence drawer display of exactly the validated citation subset. The read-only mutation request was refused before provider invocation with zero transition, command, or semantic-state mutation. V1 upgraded-history compatibility passed.

## Preservation and quality

R1–R9 behavior remains covered by the controlled Assistant matrix: 97 tests passed. Frontend typecheck, lint, and production build passed. Ruff, compileall, Alembic current/heads, and static scans passed. The deterministic Playwright suite passed 12/12 in three consecutive runs with workers=1 and retries=0.

The final sanitized evidence bundle is outside the repository and supersedes the prior partial bundle:
`C:\Users\ilyas.abarbach\Documents\amfa-s3-f15-r10-final-20260729\R10_EVIDENCE_20260729_FINAL`

Evidence manifest SHA-256: `B008844BE9CD4835F3D68D3A84DF11094B7BF6920050ACA65B3F0D81398F17AE`.

## Independent review

The provider cannot return a different valid intent or capability because both are strict one-value bindings and are rechecked by the backend. The composite follow-up cannot route to an incapable capability because its variations classify deterministically to `failure_explanation`. An evidence claim cannot complete without a selected citation when approved excerpts are available; an unselected excerpt cannot pass source-map or exact identity validation. Backend normalization cannot fabricate or replace citations. Retry cannot hide this defect: first-attempt and consecutive fresh real-Azure proofs passed. Strict validation and R1–R9 invariants were preserved.
