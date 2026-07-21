# Goal 10 Two-Phase Protocol

AMFA-225 is an integrated product proof and cannot honestly be completed on a branch that starts from the common `goal` SHA without G01–G09 implementations.

## Phase A — Acceptance harness branch

Branch `hermes/10-full-runtime-proof` owns only the reusable external fixture/acceptance harness, deterministic failure fixtures, safe real-subprocess profiles, fake-model integration suite, runtime evidence collector, cancellation/restart driver, security probes, and operator acceptance status projection where justified. It consumes frozen schemas and may use test fakes. It must not duplicate production services owned by G01–G09.

Phase A completion:

- `completion_level=harness_ready`
- `harness_ready=true`
- `branch_ready=true` when all branch-owned harness work is green
- `integration_verified=false`
- `jira_complete=false`
- every unexecuted integrated AMFA-225 criterion is listed in `blocked_integrated_criteria`

The branch may then be pushed.

## Phase B — Integrated runtime proof

After the integration coordinator merges the required Sprint 2 work and G01–G09 in dependency order, Goal 10 is resumed or recreated on the integration branch. It runs real production APIs and external fixtures through all required gates and scenarios. No production service is replaced by a test fake.

Phase B must prove Angular 18.0.x and 18.2.x through 19→20→21; one governed repair; an environment blocker without a source patch; stale proposal rejection; cancellation; backend restart recovery; assistant evidence/fallback; G13 final assurance; G14 atomic publication; G15 deterministic report; output fingerprint; and unchanged source. Human product sign-off is required.

Only Phase B may set `completion_level=integration_verified`, `integration_verified=true`, and `jira_complete=true`.
