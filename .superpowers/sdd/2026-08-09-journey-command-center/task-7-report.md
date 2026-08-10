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
