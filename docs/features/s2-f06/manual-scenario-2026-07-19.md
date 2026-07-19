# S2-F06 Manual Scenario — 2026-07-19

Use authenticated actor `operator` and a synthetic Angular 18.x single-app npm
workspace generated under an external temporary source root. Keep generated
workspace files outside this repository.

1. Start the backend and frontend and open the authoritative run page.
2. Confirm the empty Plan viewer blocks generation until prerequisite evidence
   and exact planning inputs are available.
3. Generate the plan with valid fixture data.
4. Confirm the family route, exact Stage 1 target, structured argv (`shell:
   false`), builder decision, validation/recovery/forbidden-change policies,
   and artifact checksums.
5. Refresh or disconnect/reconnect and confirm the same authoritative plan is
   rehydrated without duplicate generation or local workflow advancement.
6. Inspect the two durable events and all seven registered artifact IDs through
   the API/database evidence boundary.
7. Repeat with a stale state version, unauthorized actor, malformed command or
   tampered artifact and confirm a stable blocked/error state with no plan
   progression.

Expected evidence: plan/stage/decision/pointer records, seven immutable
artifact IDs and checksums, ordered `MIGRATION_PLAN_CREATED` and
`STAGE_PLAN_CREATED` events, and one negative-case correlation ID. Cleanup must
use only the product-owned disposable workspace action.

Status: `manual_validation_required` until a live authenticated browser run is
executed; automated FastAPI/SQLite/Artifact Store and React/SSE coverage is
recorded in `verification.md`.
