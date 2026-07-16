# S1-F14 Progress

## Delivered issues

- S1-F14-I01: deterministic baseline qualification policy and checksum-bound G03 domain rules.

## Scope boundary

The domain evaluates S1-F10 through S1-F13 evidence without executing commands,
mutating workspaces, persisting state, exposing API routes, or advancing the
workflow directly. Database/API/event/artifact persistence, frontend projection,
and the remaining Feature 14 issues are intentionally deferred.

## Rules covered

- Clean evidence qualifies under strict-clean policy.
- Known failures qualify only when fingerprints exist and company policy allows
  the explicit known-failure policy; the result remains visibly conditional.
- Failed or unproven mandatory install/build evidence cannot be approved.
- G03 approval is rejected when state, sandbox, or ExecutionProfile evidence is
  stale.
