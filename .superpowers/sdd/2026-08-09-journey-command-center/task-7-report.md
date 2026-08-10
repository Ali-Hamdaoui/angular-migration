# Task 7 report: complete semantic Pipeline through G06

## Files changed

- `frontend/src/components/control-tower/PipelineSection.tsx`
- `frontend/src/components/control-tower/PipelineStageDetail.tsx` (created)
- `frontend/src/components/control-tower/ControlTowerLayout.module.css`
- `frontend/src/components/AuthoritativeRunDashboard.tsx`
- `frontend/src/components/control-tower/__tests__/ControlTowerPresentation.test.tsx`
- `frontend/src/components/__tests__/G02ReviewPanel.test.tsx`
- `frontend/src/components/__tests__/AnalysisReviewPanel.test.tsx`
- `frontend/src/components/__tests__/FeasibilityPanel.test.tsx`
- `frontend/src/components/__tests__/PlanReviewPanel.test.tsx`
- `.superpowers/sdd/2026-08-09-journey-command-center/task-7-report.md` (created)
- `.superpowers/sdd/2026-08-09-journey-command-center/progress.md` (appended)

No backend, API-contract, transformation-panel, G07-G12, deployment, or unrelated route files changed. The existing G02-G06 production panels and hooks required no request-contract edits; their unchanged implementations are composed by the new typed Pipeline and protected by expanded regression tests.

## Intake and visual authority

Implementation started from clean reviewed HEAD `6a1b455992e6d2bc98037b494813fe506ad1d29a` in the dedicated `journey-command-center` linked worktree. Before tests or production edits, the approved `selected-journey-command-center.png` was inspected at original/native resolution. The implementation extends its flat navy, thin-border, restrained cyan/green/amber command-center system without gradients, glow, glass, shadows, emoji, handcrafted icons, a new palette, or a competing navigation model.

The complete Task 7 brief, Task 7 plan and relevant approved design sections, Task 6 report and reviewed shell contracts, TDD test-quality rules, verification rules, worktree instructions, and React best practices were read before implementation. The untouched focused baseline passed 6 files and 51/51 tests.

## Strict RED evidence

The new behavior tests were written and run before any production Pipeline or dashboard edit:

```text
npm test -- src/components/control-tower/__tests__/ControlTowerPresentation.test.tsx
Test Files: 1 failed (1)
Tests: 8 failed, 21 passed (29)
Exit code: 1
```

The eight expected failures proved that the old component still rendered eleven raw-event-inferred rows, had no six-group/twelve-milestone contract, did not preserve manual expansion against unchanged authority, mapped typed focus keys to legacy display labels, exposed pseudo-tabs without keyboard semantics, fabricated unavailable tab labels, and sent G02/G03/transformation focus to legacy rows.

## Implementation summary

- Deleted the local `steps`, `relevant`, `state`, legacy status, and display-label focus maps from `PipelineSection`. It now consumes only `JourneyMilestone[]`, typed `PipelineStageContent[]`, and optional `JourneyKey` focus.
- Rendered all twelve milestones beneath Prepare, Baseline, Understand, Decide, Transform, and Validate. Status text is visible independently of color, and every milestone uses its typed journey key for identity and focus.
- Kept exactly one expanded row. Action-required/current authority selects the initial row; an operator-selected row remains open while the same authoritative key refreshes; a genuinely new authoritative current/action-required key takes focus.
- Added `PipelineStageDetail` with real `tablist`/`tab`/`tabpanel` relationships, `aria-controls` and `aria-labelledby`, automatic roving selection/focus for ArrowLeft, ArrowRight, Home, and End, one selected tab, and only one mounted selected panel.
- Made Summary the truthful baseline tab, using `Not available from the authoritative state` when unavailable. Command output appears only for an exact command/log payload, Evidence only for artifact IDs that resolve to registered run artifacts, and Review only for an exact G02-G06 package-created event with a package checksum.
- Memoized the nontrivial stage-content projection in `AuthoritativeRunDashboard`. Component definitions and static maps remain module-level; no new hook subscription or data-fetch owner was added.
- Composed G02 source snapshot review under Readiness/Prepare, G03 baseline qualification under Baseline, parity/discovery/G04 under Discovery/Understand, compatibility/G05 under Feasibility/Decide, and MigrationPlan/G06 under Plan/Decide.
- Existing feature elements are created as typed React nodes but mount only when their stage is expanded and their selected Summary or Review tab is active. Inactive destinations, collapsed rows, unavailable tabs, and unselected tabs have no mounted feature wall or background subscription.
- Preserved Task 6 shell contracts: four destinations, subordinate Assistant, one authoritative-run hook, one transformation hook, typed `JourneyKey` handoff, no auto-navigation, and fail-closed freshness/navigation.
- Left G07-G12/Transformation workspace integration for Task 8. The three transformation route milestones render the authoritative journey state and truthful Summary only; no later decision surface was moved into this task.
- Extended regression coverage for G02-G06 authority. Assertions retain exact state versions, idempotency-key contracts, gate/package/artifact/plan/stage checksums, workspace fingerprints, comments, and 409 fail-closed/reload behavior. The G06 test exercises the real `usePlanReview` boundary through `decideG06`.

## Verification evidence

```text
npm test -- src/components/control-tower/__tests__/ControlTowerPresentation.test.tsx src/components/__tests__/G02ReviewPanel.test.tsx src/components/__tests__/AnalysisReviewPanel.test.tsx src/components/__tests__/FeasibilityPanel.test.tsx src/components/__tests__/MigrationPlanPanel.test.tsx src/components/__tests__/PlanReviewPanel.test.tsx
Test Files: 6 passed (6)
Tests: 61 passed (61)
Exit code: 0

npm test -- src/components/__tests__/AuthoritativeRunDashboard.test.tsx src/components/control-tower/__tests__/ControlTowerPresentation.test.tsx
Test Files: 2 passed (2)
Tests: 42 passed (42)
Exit code: 0

npm run typecheck
tsc --noEmit
Exit code: 0

npm run lint
eslint .
Exit code: 0

git diff --check
Exit code: 0
Only expected LF-to-CRLF working-copy notices were emitted; no whitespace errors.

npm test
Test Files: 58 passed (58)
Tests: 453 passed (453)
Exit code: 0
Duration: 67.12s
```

## Consolidated-diff self-review

The complete Task 7 diff, including the new untracked stage-detail file, was inspected once after the focused, static, and full-suite gates were green. The review checked typed journey identity; twelve-stage/six-group completeness; authoritative versus manual expansion; exact tab relationships and mounted-panel lifecycle; truthful command/evidence/review omission; G02-G06 panel placement and decision bindings; Task 6 hook/focus/navigation preservation; human-summary hierarchy; 44 px controls; visible focus; mobile containment; visual-token compliance; Task 8 exclusion; and allowlist-only scope.

Static scans found no legacy `steps`, `relevant`, `state`, or display-label focus pipeline; no hidden panel mounting; and no new gradients, shadows, filters, glow, glass, or decorative text glyphs. No scoped defect remained after the consolidated review.

## Concerns

No open Task 7 implementation concern. Expected LF-to-CRLF working-copy notices remain informational. Task 7 is implemented pending independent review and is not marked complete.

## Independent review fix round 1

Task 7 review fix round 1 was implemented from clean reviewed HEAD `c28989cbbd4faf0feb9db835cc334ad78978f510`. The five verified findings are addressed and the task remains pending independent re-review.

### Review findings addressed

- Corrected journey authority so G02 owns Readiness and G03 alone owns Baseline. Real `buildRunWorkspaceProjection` regressions cover pending and terminal G02/G03 states, including the pre-run Readiness-complete override.
- Replaced single-event evidence attribution with exact authoritative package evidence. G02 and G03 load their exact same-run package/assessment in the dashboard, validate checksums and artifact IDs, and pass the preloaded responses into embedded panels without duplicate GET ownership. G04-G06 retain artifact-bearing event IDs across later terminal decisions. IDs are resolved only against `state.artifacts`; no label, path, checksum, or category inference creates an Evidence tab.
- Hoisted the operator-expanded `JourneyKey` into the dashboard shell so Pipeline -> Evidence -> Pipeline navigation preserves the chosen row. Only a genuinely changed authoritative key or a new explicit focus changes it.
- Added configurable semantic panel headings. Standalone panels retain their existing outline; Pipeline composition renders panel headings below the Pipeline `h2`, group `h3`, and stage-detail context.
- Added a state-derived `data-tone` to the Pipeline summary. Complete is success, current is accent, action-required/blocked is warning, and unavailable/not-reached is neutral.

The consolidated self-review found one additional scoped lifecycle defect: refreshed DTOs could recreate unchanged G02/G03 event objects and repeat both GETs. A regression recreated those objects around an unrelated authoritative event; loader effects now depend on stable event IDs and package checksums.

### Strict RED/GREEN evidence

```text
G02/G03 journey ownership RED: 1 file failed; 2 failed, 29 passed
G02/G03 journey ownership GREEN: 1 file passed; 31/31

Pending/terminal G02-G06 evidence RED: 1 file failed; 2 failed, 13 skipped
Pending/terminal G02-G06 evidence GREEN: 1 file passed; 15/15

Pipeline unmount/remount expansion RED: 1 failed, 15 skipped
Pipeline unmount/remount expansion GREEN: 1 passed, 15 skipped

Embedded outline RED: 7 files failed; 8 failed, 38 skipped
Embedded outline GREEN: 7 files passed; 8 passed, 38 skipped

Summary tone RED: 1 file failed; 2 failed, 29 skipped
Summary tone GREEN: 1 file passed; 2 passed, 29 skipped

Cross-run stale G02 package RED: 1 failed, 16 skipped
Cross-run stale G02 package GREEN: 1 passed, 16 skipped

Unchanged-package duplicate GET RED: 1 failed, 17 skipped
Unchanged-package duplicate GET GREEN: 1 passed, 17 skipped
```

### Final verification

```text
npm test -- src/components/control-tower/__tests__/ControlTowerPresentation.test.tsx src/components/__tests__/G02ReviewPanel.test.tsx src/components/__tests__/AnalysisReviewPanel.test.tsx src/components/__tests__/FeasibilityPanel.test.tsx src/components/__tests__/MigrationPlanPanel.test.tsx src/components/__tests__/PlanReviewPanel.test.tsx
Test Files: 6 passed (6)
Tests: 69 passed (69)

npm test -- src/components/__tests__/AuthoritativeRunDashboard.test.tsx src/presentation/__tests__/currentAction.test.ts src/components/__tests__/SourceSnapshotPanel.test.tsx src/components/__tests__/BaselineParityPanel.test.tsx
Test Files: 4 passed (4)
Tests: 57 passed (57)

npm run typecheck
Exit code: 0

npm run lint
Exit code: 0

npm test
Test Files: 58 passed (58)
Tests: 472 passed (472)

git diff --check
Exit code: 0
Only expected LF-to-CRLF working-copy notices were emitted; no whitespace errors.
```

The narrow fix diff was self-reviewed for same-run/package validation, exact artifact identity, retained terminal evidence, request ownership and races, typed expansion persistence, heading outline, status tone, decision bindings, 409 fail-closed behavior, and Task 8 exclusion. No open scoped concern remains. Task 7 review fix round 1 is implemented pending re-review and is not marked complete.

## Independent review fix round 2

Task 7 review fix round 2 was implemented from clean reviewed HEAD `62eb1d9c119eb96cafd8e5f7c05c08799d2d2a0c`. The verified package-loading finding is addressed and the task remains pending independent re-review.

The dashboard-to-panel boundary now carries an explicit `loading | ready | unavailable | error` state instead of collapsing every non-ready response to `null`. Each state is bound to the run, created-event identity, exact package checksums, and latest gate event. A changed binding is synchronously treated as loading, late prior requests are ignored, invalid responses become unavailable, rejected GETs become error, and a safe GET-only retry starts a new request. Valid recovery restores the registered Evidence tab and the existing checksum/version-bound G02 or G03 review action.

Embedded G02/G03 panels no longer interpret an unresolved external package as true absence. Pending, invalid, and failed GETs render non-mutating loading or unavailable/error content. Only the standalone panel flow that independently proves no package exists can expose `Initialize G02 review` or `Qualify baseline`. Existing decision payloads, state versions, checksums, idempotency behavior, 409 fail-closed handling, heading composition, single GET ownership, and Task 8 boundaries remain unchanged.

### Strict RED/GREEN evidence

```text
npm test -- src/components/__tests__/AuthoritativeRunDashboard.test.tsx -t "package mutation|fails closed"
RED: Test Files 1 failed (1); Tests 6 failed, 1 passed, 17 skipped
GREEN: Test Files 1 passed (1); Tests 7 passed, 17 skipped

Broader dashboard/panel regression discovered during integration:
RED: Test Files 1 failed, 1 passed; Tests 1 failed, 29 passed
Cause: no-package runs wrote an unused unavailable record and rerendered the hook owner.
GREEN: Test Files 2 passed (2); Tests 30 passed (30)
```

### Final verification

```text
npm test -- src/components/control-tower/__tests__/ControlTowerPresentation.test.tsx src/components/__tests__/G02ReviewPanel.test.tsx src/components/__tests__/AnalysisReviewPanel.test.tsx src/components/__tests__/FeasibilityPanel.test.tsx src/components/__tests__/MigrationPlanPanel.test.tsx src/components/__tests__/PlanReviewPanel.test.tsx
Test Files: 6 passed (6)
Tests: 69 passed (69)

npm test -- src/components/__tests__/AuthoritativeRunDashboard.test.tsx src/presentation/__tests__/currentAction.test.ts src/components/__tests__/SourceSnapshotPanel.test.tsx src/components/__tests__/BaselineParityPanel.test.tsx
Test Files: 4 passed (4)
Tests: 63 passed (63)

npm run typecheck
Exit code: 0

npm run lint
Exit code: 0

npm test
Test Files: 58 passed (58)
Tests: 478 passed (478)

git diff --check
Exit code: 0
Only expected LF-to-CRLF working-copy notices were emitted; no whitespace errors.
```

The narrow fix diff was self-reviewed for explicit load-state exhaustiveness, same-run/package identity, immediate stale-response omission, request cancellation, GET-only recovery, suppression of package-creation/qualification mutations, successful Review/action recovery, unchanged package request deduplication, hook ownership, payload authority, and Task 8 exclusion. No open scoped concern remains. Task 7 review fix round 2 is implemented pending re-review and is not marked complete.

## Independent review fix round 3

Task 7 review fix round 3 was implemented from clean reviewed HEAD `1223cec549da968b28a609b1531891a73fea256b`. The verified embedded G02 decision-refresh race is addressed and the task remains pending independent re-review.

An embedded G02 panel now consumes a successful `decideG02` response immediately instead of discarding it behind the still-pending dashboard prop. The response override is valid only for the exact source review binding: run ID, package checksum, event sequence, and state version. Re-renders with the unchanged authoritative pending review therefore keep terminal controls closed, while loading or any changed authoritative binding immediately ignores the override and cannot disclose stale review data. The standalone panel, exact decision payload, checksum/version binding, reviewer draft, and 409 fail-closed behavior are unchanged.

### Strict RED/GREEN evidence

```text
npm test -- src/components/__tests__/G02ReviewPanel.test.tsx -t "keeps an embedded successful decision closed"
RED: Test Files 1 failed (1); Tests 1 failed, 6 skipped
GREEN: Test Files 1 passed (1); Tests 1 passed, 6 skipped
```

### Final verification

```text
npm test -- src/components/control-tower/__tests__/ControlTowerPresentation.test.tsx src/components/__tests__/G02ReviewPanel.test.tsx src/components/__tests__/AnalysisReviewPanel.test.tsx src/components/__tests__/FeasibilityPanel.test.tsx src/components/__tests__/MigrationPlanPanel.test.tsx src/components/__tests__/PlanReviewPanel.test.tsx
Test Files: 6 passed (6)
Tests: 70 passed (70)

npm test -- src/components/__tests__/AuthoritativeRunDashboard.test.tsx src/presentation/__tests__/currentAction.test.ts src/components/__tests__/SourceSnapshotPanel.test.tsx src/components/__tests__/BaselineParityPanel.test.tsx
Test Files: 4 passed (4)
Tests: 63 passed (63)

npm run typecheck
Exit code: 0

npm run lint
Exit code: 0

npm test
Test Files: 58 passed (58)
Tests: 479 passed (479)

git diff --check
Exit code: 0
Only expected LF-to-CRLF working-copy notices were emitted; no whitespace errors.
```

The narrow fix diff was self-reviewed for exact override identity, immediate post-decision control closure, stale-data omission across binding changes, unchanged G02 payload and 409 behavior, standalone compatibility, and Task 8 exclusion. No open scoped concern remains. Task 7 review fix round 3 is implemented pending re-review and is not marked complete.
