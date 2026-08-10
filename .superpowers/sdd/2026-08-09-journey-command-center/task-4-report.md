# Task 4 report: revision-safe migration preparation

## Files changed

- `frontend/src/presentation/setupReadiness.ts` (created)
- `frontend/src/presentation/__tests__/setupReadiness.test.ts` (created)
- `frontend/src/api/migrations.ts`
- `frontend/src/components/MigrationSetupForm.tsx`
- `frontend/src/components/MigrationSetupForm.module.css`
- `frontend/src/components/__tests__/MigrationSetupForm.test.tsx`
- `.superpowers/sdd/2026-08-09-journey-command-center/task-4-report.md` (created)
- `.superpowers/sdd/2026-08-09-journey-command-center/progress.md` (appended)

The route wrapper `frontend/src/app/migrations/new/page.tsx` did not require a presentation or accessibility adjustment and was left unchanged.

## RED evidence

The required focused command was run before production implementation:

```text
npm test -- src/presentation/__tests__/setupReadiness.test.ts src/components/__tests__/MigrationSetupForm.test.tsx
Exit code: 1
Test Files: 2 failed
Tests: 15 failed
```

- The pure suite collected zero tests because `@/presentation/setupReadiness` did not exist yet.
- All 15 component tests failed against the former Validate/Start UI because the semantic four-step journey, operation rows, Check readiness action, revision invalidation, authoritative source review, and G01 handoff were not implemented.

Three follow-up RED checks caught implementation gaps before their fixes:

- Missing source analysis incorrectly implied `Custom builder detected: No`: 1 failed, 32 skipped.
- An edit during a deferred path request left the recheck action disabled, and the source operation omitted its warning: 2 failed, 13 skipped.
- An otherwise complete preflight missing `decision_history` passed the runtime guard: 1 failed, 14 skipped.

Each focused mutation was then made GREEN without weakening assertions.

## Implementation summary

- Added pure exact-status adapters for path, environment, source, and production preflight. Unknown strings fail closed to `unavailable`; explicit waiting, running, unavailable, and outdated lifecycle states override backend presentation without substring inference.
- Added a truthful source-review adapter using only returned evidence. Angular version prefers resolved, then declared, then family; builder name remains explicitly unavailable; custom-builder presence is Yes/No only when an authoritative source snapshot exists.
- Expanded only the local frontend `SourceAnalysisResult` type to the existing backend response contract.
- Rebuilt setup as a semantic four-step Project, Readiness, Source review, and locked Create run journey with four operation rows visible at all times.
- Implemented controlled Project inputs with one `onChange` path, a synchronously updated revision ref, one increment per actual value change, immediate active-binding invalidation, and outdated prior evidence.
- Guarded every awaited chain boundary with both the request-attempt and revision checks. Late success, rejection, and finally work from an old revision cannot authorize or overwrite the current revision.
- Preserved the authoritative order: path validation; environment refresh and source analysis in parallel; then production preflight. Independent secondary failures retain the successful sibling and prevent preflight when an identifier is absent. Returned blocked secondary snapshots retain their IDs and continue to authoritative preflight.
- Constructed the active binding only after a complete, runtime-schema-valid, current-revision preflight. Only passed and warning preflights with unexpired evidence expose `/preflights/{preflight_id}`; blocked, ineligible, expired, stale, unavailable, and outdated outcomes never do.
- Kept Step 4 locked and explicit that G01 review/approval on the existing route unlocks authoritative creation. Setup creates no run and never claims approval.
- Replaced hard-coded component colors with Task 3 foundation variables and used flat surfaces, thin borders, text-plus-color states, responsive one-column layout, wrapping identifiers, and normal-flow 44 px actions.

## Verification evidence

Final evidence after the consolidated-review correction:

```text
npm test -- src/presentation/__tests__/setupReadiness.test.ts src/components/__tests__/MigrationSetupForm.test.tsx
Test Files: 2 passed (2)
Tests: 48 passed (48)
Exit code: 0

npm run typecheck
tsc --noEmit
Exit code: 0

npm run lint
eslint .
0 errors, 0 warnings
Exit code: 0

git diff --check
Exit code: 0
Only LF-to-CRLF working-copy notices were emitted; no whitespace errors.

npm test
Test Files: 56 passed (56)
Tests: 355 passed (355)
Exit code: 0
Duration: 40.91s
```

Baseline before Task 4 was 55 files and 316 tests, all passing.

## Consolidated-diff self-review

Reviewed the exact Task 4 diff once for the required concerns:

- Revision races and stale IDs: found the in-flight edit re-enable issue during implementation and corrected it; the final attempt-plus-revision guards cover success, rejection, and finally paths. Rechecks use new operation scopes and only their own four returned IDs.
- Evidence/status truthfulness: exact mappings fail closed; warnings remain warnings; blocker and warning messages remain visible; missing evidence is unavailable rather than inferred.
- Source accuracy: local type matches the backend contract; Angular version, topology, package manager, count, lockfile, confidence, target, and custom-builder flag are response-derived; no builder name is fabricated.
- Runtime authority: found one Important schema-validation gap during the consolidated review (`decision_history` and other full-contract fields were not all required). Added a RED regression and strengthened the guard before final verification.
- Route/run authority: the only navigation is `/preflights/{activeBinding.preflightId}` and no local run creation or G01 approval is exposed.
- Accessibility and keyboard semantics: one route `h1`, logical headings, labeled controlled fields, ordered journey, native buttons, one restrained live status, alerts only for actionable request failures, visible text states, and normal-flow actions.
- Responsive/visual constraints: narrow layouts collapse to one column, identifiers wrap, CSS uses foundation variables, and there are no gradients, glow, arbitrary shadows, hard-coded palette colors, text-glyph icons, or new assets.
- Encoding and scope: touched source contains no mojibake. Only the Task 4 allowlist plus this report and ledger entry changed.

## Concerns

No open Task 4 concern. Git reports repository line-ending conversion notices for edited frontend files, but `git diff --check` is clean.

## Fix round 1/5

### Reviewer findings addressed

- Active binding now fails closed across the complete chain. Path, environment, source, and preflight mapped states must each be `passed` or `warning`, and the preflight must be unexpired. Unknown prerequisite snapshots and blocked secondary environment/source snapshots still contribute their returned identifiers to the authoritative production-preflight request; blocked or ineligible path validation stops before secondary checks and preflight. A passed final preflight cannot expose G01 navigation for an unavailable or blocked secondary prerequisite.
- `SetupBinding` now preserves the authoritative `expiresAt`. A cleanup-safe, long-delay-rescheduling timer marks the preflight outdated and removes navigation when it elapses. The click handler independently checks revision and expiry immediately before routing.
- Runtime validation now checks every declared production-preflight field, string arrays, artifact entries, and every nested G01 decision field. Decision enums, timestamps, primitive types, and preflight/gate ID relationships fail closed. A later valid recheck recovers normally.
- Environment, source, and preflight messages now remain verbatim. The existing path-code translation map is used only for path-rule evidence.

### Fix-round RED evidence

```text
npm test -- src/presentation/__tests__/setupReadiness.test.ts src/components/__tests__/MigrationSetupForm.test.tsx
Exit code: 1
Test Files: 1 failed, 1 passed
Tests: 9 failed, 47 passed (56 total)
```

The nine expected failures were five unknown/blocked prerequisite authorization cases, one non-path message translation case, one malformed nested decision-history case, automatic expiry invalidation, and click-time expiry protection.

### Fix-round GREEN and static evidence

```text
npm test -- src/presentation/__tests__/setupReadiness.test.ts src/components/__tests__/MigrationSetupForm.test.tsx
Test Files: 2 passed (2)
Tests: 56 passed (56)
Exit code: 0
Duration: 5.03s

npm run typecheck
Exit code: 0

npm run lint
0 errors, 0 warnings
Exit code: 0

git diff --check
Exit code: 0
Only LF-to-CRLF working-copy notices were emitted; no whitespace errors.

npm test
Test Files: 56 passed (56)
Tests: 363 passed (363)
Exit code: 0
Duration: 40.34s
```

### Fix-diff self-review

Reviewed only the fix diff and the original authorization regression context. The four mapped states gate binding; blocked secondary IDs still flow into preflight; active binding expiry is ref-synchronized, timer-cleaned, safely rescheduled, and rechecked on click; nested decision validation covers every typed field and relational IDs; non-path evidence remains verbatim; revision invalidation and G01-only routing remain intact. No new style, route, API, backend, or file-scope change was introduced. No open concern remains for fix round 1.

## Fix round 2/5

The production-preflight runtime guard now requires the authoritative gate identifier to be exactly `G01`. A structurally valid snapshot and nested decision history that consistently claim another gate therefore fail schema validation, render production preflight as unavailable, and cannot expose the Review action.

### Fix-round RED evidence

```text
npm test -- src/components/__tests__/MigrationSetupForm.test.tsx -t "rejects a structurally consistent non-G01 production preflight"
Exit code: 1
Test Files: 1 failed (1)
Tests: 1 failed, 23 skipped (24 total)
```

The consistent `G99` fixture incorrectly rendered a passed preflight and Review action before the exact gate guard was added.

### Fix-round GREEN and static evidence

```text
npm test -- src/components/__tests__/MigrationSetupForm.test.tsx -t "rejects a structurally consistent non-G01 production preflight"
Test Files: 1 passed (1)
Tests: 1 passed, 23 skipped (24 total)
Exit code: 0

npm test -- src/presentation/__tests__/setupReadiness.test.ts src/components/__tests__/MigrationSetupForm.test.tsx
Test Files: 2 passed (2)
Tests: 57 passed (57)
Exit code: 0

npm run typecheck
Exit code: 0

npm run lint
Exit code: 0

git diff --check
Exit code: 0
Only LF-to-CRLF working-copy notices were emitted; no whitespace errors.

npm test
Test Files: 56 passed (56)
Tests: 364 passed (364)
Exit code: 0
```

### Fix-diff self-review

Reviewed only the narrow round-2 diff and the production-preflight authorization regression context. The runtime guard now accepts exactly `G01`; the new consistent-`G99` regression verifies schema rejection, unavailable presentation, and absent Review navigation. No other schema, lifecycle, routing, API, backend, or file-scope behavior changed. No open concern remains for fix round 2.
