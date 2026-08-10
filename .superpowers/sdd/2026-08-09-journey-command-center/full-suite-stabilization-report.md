# Full-suite stabilization report

## Scope

This change stabilizes the Assistant request-retry contract and the Migration Plan tab-selection contract. It changes only the four permitted frontend source/test files plus this report. The pre-existing Task 3 work remains unmodified and unstaged.

## Workspace evidence before edits

`git status --short`:

```text
 M .superpowers/sdd/2026-08-09-journey-command-center/task-3-report.md
 M frontend/package-lock.json
 M frontend/src/app/globals.css
 M frontend/src/components/ControlTowerShell.module.css
 M frontend/src/components/control-tower/ControlTowerHeader.tsx
 M frontend/src/components/control-tower/ControlTowerLayout.module.css
 M frontend/src/components/control-tower/ControlTowerSidebar.tsx
 M frontend/src/components/control-tower/__tests__/ControlTowerPresentation.test.tsx
```

`git diff --name-only de9b4517e018748c809fd312eacc6a67ab2a8d7b`:

```text
.superpowers/sdd/2026-08-09-journey-command-center/task-3-report.md
frontend/package-lock.json
frontend/src/app/globals.css
frontend/src/components/ControlTowerShell.module.css
frontend/src/components/control-tower/ControlTowerHeader.tsx
frontend/src/components/control-tower/ControlTowerLayout.module.css
frontend/src/components/control-tower/ControlTowerSidebar.tsx
frontend/src/components/control-tower/__tests__/ControlTowerPresentation.test.tsx
```

The index was empty before edits (`git diff --cached --name-only` produced no output).

## Deterministic RED evidence

Command:

```powershell
npm test -- src/components/__tests__/AssistantPanel.test.tsx src/components/__tests__/MigrationPlanPanel.test.tsx
```

Exit code: `1`.

Exact failing summary:

```text
 ❯ src/components/__tests__/MigrationPlanPanel.test.tsx (5 tests | 1 failed) 394ms
     × preserves the Builder tab after a same-checksum authoritative refresh 85ms
 ❯ src/components/__tests__/AssistantPanel.test.tsx (9 tests | 1 failed) 989ms
     × keeps retry available when the stream disconnects after a 503 request failure 252ms

 Test Files  2 failed (2)
      Tests  2 failed | 12 passed (14)
   Start at  02:30:14
   Duration  3.77s (transform 416ms, setup 425ms, import 823ms, tests 1.38s, environment 3.61s)
```

Exact Assistant failure diagnostic:

```text
FAIL  src/components/__tests__/AssistantPanel.test.tsx > AssistantPanel authoritative rendering > keeps retry available when the stream disconnects after a 503 request failure
TestingLibraryElementError: Unable to find an accessible element with the role "button" and name "Retry"
```

At that failure point the DOM contained both alerts:

```text
Reconnecting to persisted conversation…
Assistant request failed POST /api/v1/runs/run-1/assistant/messages returned 503
```

Exact Migration Plan failure diagnostic:

```text
FAIL  src/components/__tests__/MigrationPlanPanel.test.tsx > MigrationPlanPanel > preserves the Builder tab after a same-checksum authoritative refresh
Error: expect(element).toHaveAttribute("aria-selected", "true") // element.getAttribute("aria-selected") === "true"

Expected the element to have attribute:
  aria-selected="true"
Received:
  aria-selected="false"
```

These failures prove the intended races rather than test-harness errors. The Assistant API mock now explicitly provides a stable pending `streamAssistantEvents` default, and its regression test rejects one controlled stream only after the 503 is visible. The Migration Plan test controls the same-checksum refresh and waits for its loading state to complete.

## Minimal production changes

- Assistant retry availability is stored separately from transport presentation state. It is cleared at submit/retry start and request success, set on request failure, and no longer disappears when the stream changes transport state to `reconnecting`.
- Migration Plan remembers the previous nonempty plan checksum. Initial success and same-checksum/status-only success preserve the selected tab; a transition from one loaded nonempty checksum to a different nonempty checksum resets to Commands.

## GREEN and static evidence

Focused command:

```powershell
npm test -- src/components/__tests__/AssistantPanel.test.tsx src/components/__tests__/MigrationPlanPanel.test.tsx
```

```text
 Test Files  2 passed (2)
      Tests  14 passed (14)
   Start at  02:31:35
   Duration  3.95s (transform 523ms, setup 426ms, import 939ms, tests 1.46s, environment 3.52s)
```

Additional required checks:

- `npm run typecheck` — exit `0`; `tsc --noEmit` produced no diagnostics.
- `npx eslint src/components/AssistantPanel.tsx src/components/__tests__/AssistantPanel.test.tsx src/components/MigrationPlanPanel.tsx src/components/__tests__/MigrationPlanPanel.test.tsx` — exit `0`; no output.
- `git diff --check` — exit `0`; no whitespace errors. Git printed LF-to-CRLF working-copy warnings only.

Complete frontend suite, run once after the focused/static gates with the pending Task 3 diff present:

```powershell
npm test
```

```text
 Test Files  55 passed (55)
      Tests  314 passed (314)
   Start at  02:32:08
   Duration  39.81s (transform 6.13s, setup 16.85s, import 16.40s, tests 33.34s, environment 165.12s)
```

## Self-review

- Assistant state machine: request failure/retry availability is independent from `loading`, `ready`, `failed`, and `reconnecting` transport/presentation state. The 503 error, reconnect feedback, optimistic failed question, failed-message retry binding, and Retry control coexist after stream rejection. Starting any new submit or retry clears the old request failure; success clears it again.
- Assistant cleanup and mocks: the existing active flag, `AbortController.abort()`, and reconnect-timer cleanup are unchanged. Tests mock the current streaming API directly with a stable pending default; the obsolete EventSource shim was removed. No timeout was added or increased.
- Migration Plan state machine: the checksum ref ignores empty/initial values, updates on successful nonempty projections, preserves Builder for same-checksum and status-only refreshes, and resets to Commands only when both the previous and next checksums are nonempty and different.
- Assertions remain behavior-based and were not weakened. No retry loop, timeout inflation, CSS, package, configuration, backend, hook, or Task 3 file was changed for stabilization.

## Staged-file proof

The index was verified immediately before commit with `git diff --cached --name-only` and contained exactly:

```text
.superpowers/sdd/2026-08-09-journey-command-center/full-suite-stabilization-report.md
frontend/src/components/AssistantPanel.tsx
frontend/src/components/MigrationPlanPanel.tsx
frontend/src/components/__tests__/AssistantPanel.test.tsx
frontend/src/components/__tests__/MigrationPlanPanel.test.tsx
```

No Task 3 CSS, package, status, disclosure, icon, test, or report file was staged.

## Concerns

None within the stabilization scope. The eight pre-existing Task 3 modifications remain intentionally uncommitted and unstaged for their owning implementer.
