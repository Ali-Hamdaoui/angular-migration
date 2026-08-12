# Task 6 report: journey command center shell and operator Overview

## Files changed

- `frontend/src/hooks/useTransformation.ts`
- `frontend/src/hooks/__tests__/useTransformation.test.tsx` (created)
- `frontend/src/components/control-tower/RunJourneyStrip.tsx` (created)
- `frontend/src/components/control-tower/CurrentActionCard.tsx` (created)
- `frontend/src/components/control-tower/OperatorOverview.tsx` (created)
- `frontend/src/components/control-tower/ControlTowerSidebar.tsx`
- `frontend/src/components/control-tower/ControlTowerHeader.tsx`
- `frontend/src/components/control-tower/ControlTowerLayout.module.css`
- `frontend/src/components/control-tower/__tests__/ControlTowerPresentation.test.tsx`
- `frontend/src/components/AuthoritativeRunDashboard.tsx`
- `frontend/src/components/__tests__/AuthoritativeRunDashboard.test.tsx`
- `frontend/src/components/TransformationPanel.tsx` (minimal hook-call compatibility only)
- `.superpowers/sdd/2026-08-09-journey-command-center/task-6-report.md` (created)
- `.superpowers/sdd/2026-08-09-journey-command-center/progress.md` (appended)

No backend, API-contract, deployment, or unrelated route files changed.

## Intake and visual authority

Implementation started from reviewed HEAD `4076f669cebc946ee39301ba859acc07e02bb109` in the dedicated `journey-command-center` worktree. Before tests or production edits, the approved `selected-journey-command-center.png` was inspected at original/native resolution. The Task 6 brief, relevant plan and design sections, Task 2 presentation modules and tests, Task 3 visual foundation, TDD and verification instructions, and React best practices were read before implementation.

The pre-edit focused baseline was green at 2 files and 25/25 tests.

## RED evidence

The hook suite was written and run before changing production hook code:

```text
npm test -- src/hooks/__tests__/useTransformation.test.tsx
Exit code: 1
Test Files: 1 failed (1)
Tests: 6 failed (6)
Unhandled errors: 2
```

The failures proved that the prior hook ignored `{ enabled, refreshKey }`, issued requests while disabled, treated the options object as a refresh key, duplicated loads, and had no protection against late results after run/toggle changes.

The first shell RED against the old eleven-destination navigation was 1 failed out of 14 dashboard tests. After expanding the shell and presentation coverage, both focused component files failed: the dashboard had 9 failures and 3 passes, while the presentation suite could not load because `OperatorOverview` did not yet exist. Production shell work began only after those expected failures were recorded.

## Implementation summary

- Replaced the eleven-destination shell with exactly four primary destinations: Overview, Pipeline, Evidence, and Diagnostics, using the required Lucide icons. The assistant remains functional in a subordinate, separated slot and is not a destination.
- Added a skip link, one route `h1`, semantic navigation and content regions, text-bearing statuses, 44 px controls, visible focus through the existing foundation, and one-column behavior at `max-width: 767px`.
- Kept exactly one `useAuthoritativeRun` call and one `useTransformation` call in the dashboard. Inactive Pipeline and Diagnostics content unmounts, avoiding hidden feature walls and background fetching.
- Enabled transformation only for `STAGED_MIGRATION` or exact membership in `TRANSFORMATION_EVENT_TYPES`. The refresh key is the latest matching event sequence, with no substring inference.
- Made `useTransformation` disabled-request-free and race-safe across run ID, enable/disable, refresh key, manual refresh, and late completion. Independent projection/execution requests begin together. Same-run background failures retain the last confirmed projection; only run changes reset confirmed data.
- Memoized the typed `RunWorkspaceProjection` and artifact presentations, then passed presentation objects into Overview rather than re-inferring backend event semantics in components.
- Built the accessible operator Overview with the full journey strip, current action, Completed/Now/Next, human evidence titles, and a native closed Technical details disclosure. Run identifiers, versions, counts, raw events, checksums, and transformation identifiers remain in Technical details.
- Current-action emphasis can highlight Pipeline but never changes the active destination. Only an operator click navigates and focuses a stage. Refreshing state keeps confirmed context, removes fresh-state navigation, and permits Diagnostics inspection only through an explicit click after recovery.
- Preserved truthful early Pipeline, Evidence, and Diagnostics content without fabricated progress, actions, evidence, or optimistic transitions. `TransformationPanel` changed only for the new enabled hook-call signature required by the brief.
- Covered blocked transformation, running command, verified completion, no-data, reconnecting, event-gap recovery, incompatible run IDs, unmount boundaries, exact event enablement, and stale-response races.

## Verification evidence

```text
npm test -- src/hooks/__tests__/useTransformation.test.tsx src/components/__tests__/AuthoritativeRunDashboard.test.tsx src/components/control-tower/__tests__/ControlTowerPresentation.test.tsx
Test Files: 3 passed (3)
Tests: 38 passed (38)
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
Tests: 433 passed (433)
Exit code: 0
Duration: 76.88s
```

Static checks also confirmed exactly one `useAuthoritativeRun` and one `useTransformation` call in the dashboard, and no gradients, shadows, glow, glass filters, mojibake, or new hard-coded visual effects in touched production files.

## Consolidated-diff self-review

The complete Task 6 frontend diff was inspected once after the initial focused, typecheck, and diff gates were green. The review checked hook ownership and request lifecycles; exact event-type enablement; four-destination navigation; absence of auto-navigation; inactive-workspace unmounting; typed presentation boundaries; technical-detail disclosure; fail-closed refreshing and incompatible states; semantic hierarchy; responsive token use; and file-scope compliance.

The final scoped scan found no competing hook subscription, old primary navigation item, forbidden visual treatment, or hidden mounted fetching surface. The existing early Pipeline remains intentionally partial for Task 7, and Transformation remains absent as a destination until Task 8.

## Concerns

No open Task 6 implementation concern. Expected LF-to-CRLF working-copy notices remain informational; `git diff --check` is clean. Task 6 is implemented pending independent review and is not marked complete.

## Review fix round 1/5

The five Important findings and one Minor finding were verified against commit `495c3446378dbf555fd22e6473b4c758db7fbb06`, then reproduced before their production corrections:

```text
Authority/background refresh: 2 failed, 37 skipped across 2 files.
JourneyKey pipeline focus: 2 failed, 22 skipped; exact G02/G03/route follow-up: 3 failed, 22 skipped.
Disable/re-enable stalled refresh: 1 failed, 6 skipped.
Assistant sidebar flow: 1 failed, 11 skipped.
Mobile journey window/disclosure: 1 failed, 23 skipped.
Accessible Pipeline badge: 1 failed, 23 skipped.
Exact G02 readiness attribution follow-up: 1 failed, 26 skipped.
```

The failures showed that same-run transformation refresh errors left navigation enabled, typed journey keys were compared to display labels, confirmed same-run state remained visually disabled during a stalled re-enable, the subordinate Assistant launcher remained fixed, mobile rendered no Previous/Current/Next view or full disclosure, the action badge was excluded from the accessible name, and G02/G03 shared an imprecise stage key.

The narrow correction adds typed current-action authority with `current | refreshing` freshness and `permitted | withheld` navigation. `buildRunWorkspaceProjection` now receives transformation freshness explicitly, so a same-run background failure keeps the confirmed journey while withholding action navigation until the hook clears its refresh error after a successful refresh. `CurrentActionCard` uses the typed permission rather than matching title text.

`focusStage` is now `JourneyKey`. The legacy Pipeline maps typed keys deterministically without expanding Task 7 scope: G02/readiness opens **Source review & G02**, G03/baseline opens **Baseline qualification**, and later planning/transformation/validation keys open the available **G03 readiness** handoff row. G02 and G03 now receive distinct typed keys from the Task 2 presentation module.

Re-enabling transformation for the same run immediately restores confirmed `ready` status while the new projection request is still pending. The request remains generation-safe, and disabled or changed-run late responses retain their existing protections.

The Assistant slot now overrides the dock container into normal sidebar flow at desktop and mobile widths while the existing expanded popup remains fixed and the Assistant state machine remains unchanged. The mobile journey uses a typed Previous/Current/Next window anchored on the first action-required, blocked, or current milestone, plus a native disclosure containing the complete authoritative journey. No viewport sniffing was added. The Pipeline badge is visible text in the accessible button name.

Final review-fix verification:

```text
npm test -- src/hooks/__tests__/useTransformation.test.tsx src/components/__tests__/AuthoritativeRunDashboard.test.tsx src/components/control-tower/__tests__/ControlTowerPresentation.test.tsx src/presentation/__tests__/currentAction.test.ts src/components/__tests__/AssistantPanel.test.tsx
Test Files: 5 passed (5)
Tests: 84 passed (84)
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
Tests: 443 passed (443)
Exit code: 0
Duration: 79.02s
```

### Review-fix consolidated narrow self-review

- Authority: connection recovery, incompatible run IDs, and transformation background refresh failure all create explicit refreshing/withheld presentation authority. Successful same-run recovery removes only the refresh error and restores the confirmed action/navigation.
- Pipeline: dashboard state, current-action callbacks, and Pipeline props share `JourneyKey`; no display string crosses that boundary. The compatibility table is limited to existing legacy rows and preserves the Task 7 rewrite boundary.
- Hook lifecycle: confirmed same-run projection identity is retained across disable/re-enable, status becomes ready immediately, and the stalled request cannot bypass generation guards.
- Assistant: closed/minimized launchers remain after the four primary controls in normal sidebar flow on desktop/mobile; the expanded dialog continues to use the existing fixed popup and state machine.
- Journey/accessibility: the full desktop strip remains semantic; mobile exposes typed Previous/Current/Next labels and a native full-journey disclosure; the action-required badge participates in the control name. Controls retain 44 px targets and no JavaScript viewport branching was introduced.
- Scope: the diff contains only the Task 6 shell/hook/presentation files, the authorized Task 2 presentation module/tests, the existing Assistant test, this report, and the ledger. No backend, API, deployment, domain mutation, hidden fetching wall, palette, or navigation-model change was introduced.

No open review-fix concern. Task 6 remains implemented pending independent re-review and is not marked complete.
