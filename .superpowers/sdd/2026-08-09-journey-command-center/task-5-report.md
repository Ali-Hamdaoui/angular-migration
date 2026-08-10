# Task 5 report: shared governed gate review and G01

## Files changed

- `frontend/src/components/gates/GateReview.tsx` (created)
- `frontend/src/components/gates/GateDecisionPanel.tsx` (created)
- `frontend/src/components/gates/GateReview.module.css` (created)
- `frontend/src/components/gates/__tests__/GateReview.test.tsx` (created)
- `frontend/src/components/G01ReviewPanel.tsx`
- `frontend/src/components/G01ReviewPanel.module.css`
- `frontend/src/components/__tests__/G01ReviewPanel.test.tsx`
- `frontend/src/app/preflights/[preflightId]/page.tsx`
- `frontend/src/app/preflights/[preflightId]/PreflightReviewPage.module.css`
- `.superpowers/sdd/2026-08-09-journey-command-center/task-5-report.md` (created)
- `.superpowers/sdd/2026-08-09-journey-command-center/progress.md` (appended)

## RED evidence

The exact required focused command ran before any production edit:

```text
npm test -- src/components/gates/__tests__/GateReview.test.tsx src/components/__tests__/G01ReviewPanel.test.tsx
Exit code: 1
Test Files: 2 failed (2)
Tests: 16 failed, 4 passed (20 runnable)
```

The shared suite collected zero tests because `@/components/gates/GateReview` did not exist. The 16 G01 failures covered the missing governed hierarchy, exact approval-with-comment behavior, blocked legal choices, terminal outcomes, failed-closed unknowns, 409 reconciliation, and monotonic refresh behavior.

Follow-up RED checks caught shared reuse and lifecycle gaps before their fixes:

- Shared generated IDs, terminal outcome wording, and missing artifact-link metadata: 7 failed, 5 passed.
- Wrong-gate binding and idle expiry/click-time expiry: 2 failed, 20 skipped.
- Malformed `expires_at`: 1 failed, 1 passed, 22 skipped; the long-horizon rescheduling assertion already passed against the deliberate reschedule tick.
- Approved live expiry and stale rendered decision/run controls: 3 failed, 23 skipped before the lifecycle scheduler and click-time visual invalidation were extended; 3 passed after the fix.

## Implementation summary

- Added a pure shared `GateReview` composition with the governed reading order, authoritative status presentation, terminal outcome cards, explicit empty states, human evidence groups, caller-supplied artifact links, and native collapsed Technical details.
- Terminal models discard supplied reviewer controls from the DOM. Unknown states stay neutral and non-actionable. Reusable instances use generated label targets rather than static IDs.
- Added the controlled `GateDecisionPanel` with a labeled textarea, three visible legal decisions, per-decision disabled state, and all-control busy disabling.
- Adapted G01 through an exact authoritative-state mapper. Approved-with-comment maps to terminal approved while preserving its exact label/comment; modification requested remains distinct; stale, expired, malformed, inconsistent, wrong-gate, and unknown states fail closed.
- Kept blocked pending reviews actionable only for modification or rejection. Approval remains disabled.
- Preserved the exact decision contract: empty/whitespace approval sends `approved` with `null`; nonempty approval sends `approved_with_comment` and preserves the original comment; modification and rejection retain a nonempty comment and normalize empty input to `null`.
- Preserved the authoritative create/start/storage/deep-link chain and active-run conflict recovery. Run creation is absent while a decision is pending, enabled only after approved/approved-with-comment, and disabled for every other terminal state.
- Added automatic decision-409 reload with preserved comments, changed-evidence announcement, no false success, and a reload action on failure. Refresh merging is monotonic by state version and prevents terminal-to-pending regression on equal versions.
- Added cleanup-safe expiry scheduling for every valid future non-expired outcome, with long-delay clamping and deliberate rescheduling. Pending and approved gates visibly become expired at the deadline; immediate submit/start guards also invalidate stale rendered controls and announce the lifecycle change. Invalid expiry timestamps fail closed.
- Replaced substring artifact inference with the exact five-name map. Unknown filenames remain visible with neutral Available evidence meaning. Artifact IDs, paths, checksums, versions, reservations, timestamps, and event details remain under Technical details.
- Kept the existing event hook as the sole subscription. Connection presentation is secondary and non-live.
- Added route request cancellation and token-only flat loading/error surfaces. Touched styles contain no gradients, glow, shadows, hard-coded palette colors, or mojibake. Reviewer controls are sticky on desktop and return to normal one-column flow at 767 px.

## Verification evidence

```text
npm test -- src/components/gates/__tests__/GateReview.test.tsx src/components/__tests__/G01ReviewPanel.test.tsx
Test Files: 2 passed (2)
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
Only LF-to-CRLF working-copy notices were emitted; no whitespace errors.

npm test
Test Files: 57 passed (57)
Tests: 397 passed (397)
Exit code: 0
Duration: 40.89s
```

The pre-Task-5 baseline was 56 files and 364 tests, all passing.

## Consolidated-diff self-review

The staged Task 5 frontend diff was inspected exactly once after focused, static, and full gates were green:

- Terminal safety: approved, rejected, modification-requested, stale, expired, and unknown models render outcomes with zero reviewer buttons. Approved-with-comment retains its exact human outcome and latest backend comment. Every valid future state is scheduled to visibly expire, including approved run authorization, and stale click handlers update the rendered lifecycle immediately.
- G01 legal decisions: pending passed/warning states expose all three actions; blocked pending disables approval only; wrong gate, malformed expiry, inconsistent, and unknown values fail closed without substring inference.
- 409/races: stale decisions never report success; authoritative reload preserves the comment; lower-version and equal-version pending refreshes cannot replace newer terminal evidence.
- Run authority: create/start payloads, storage key, active-run recovery, and final route are unchanged. Only authoritative approval enables the separate run action.
- Evidence and disclosure: exact artifact mapping and encoded backend links are intact. Presence means only Available evidence. Technical identifiers and raw artifact metadata remain closed by default and wrap.
- Accessibility: one route `h1`, generated IDs, semantic headings/lists, a native disclosure, 44 px actions, visible focus inherited from the foundation, one live notice, and text-plus-icon/color status meaning.
- Responsive and visual constraints: flat tokenized navy surfaces, thin semantic borders, no new palette values, desktop sticky review controls, and normal-flow one-column mobile layout without fixed widths.
- Encoding and scope: touched source contains no mojibake. Only the Task 5 allowlist plus this report and ledger checkpoint changed.

## Concerns

No open Task 5 concern. Git reports expected line-ending conversion notices for edited frontend files; `git diff --check` remains clean.

## Expiry fix self-review

After the consolidated review, the narrow live-expiry correction was inspected once. The cleanup-safe scheduler now covers pending, approved, rejected, modification-requested, and stale future evidence so authoritative expiry precedence becomes visible without interaction. Expired and unknown states schedule nothing. Both decision and run click paths recompute status from the current clock before mutation, update `now`, and show one informational notice when a rendered control has become stale. The three new fake-time regressions prove pending click invalidation, approved live expiry/run disablement, and approved stale-click invalidation. No API, run-chain, refresh, style, route, or file-scope behavior changed.

## Review fix round 1/5

All four Important review findings were reproduced RED before their production corrections:

```text
npm test -- src/components/gates/__tests__/GateReview.test.tsx src/components/__tests__/G01ReviewPanel.test.tsx
Test Files: 2 failed (2)
Tests: 19 failed, 34 passed (53)
Exit code: 1
```

The initial RED covered failed-409 evidence freshness and recovery, runtime package/binding validation, late decision-response races, and embedded-safe headings. Contract audit follow-ups then reproduced four focused failures for the backend's equal pre-transition decision version, optional legacy layout metadata, malformed history rendering, and invalid-refresh recovery. The final two narrow boundaries reproduced a wrong-preflight refresh and a malformed post-decision candidate before those fixes.

The correction adds a fail-closed G01 authorization boundary for exact preflight/gate identity, live reservation, source/target/checksum/version/timestamp bindings, required backend evidence references, safe findings, and safe decision history. Invalid higher-version refreshes are rejected before monotonic comparison, while valid evidence can recover an invalid current package. A failed automatic 409 reload marks retained evidence unavailable and non-actionable; accepted manual or event reloads restore authority from the new snapshot, clear the stale error, and preserve the reviewer comment.

Decision responses now merge against the latest ref-held snapshot. The real backend equal-version response is accepted only while the latest same-bound package is fresh and pending, the response matches the submitted decision, its ID is absent, and the constructed terminal candidate passes the complete runtime validator. Lower, duplicate, differently bound, malformed, or terminal-superseded results cannot mutate state or announce success. This preserves the ordinary local transition and the existing reverse refresh race.

`GateReview` now defaults to an embedded-safe `h2` and exposes a typed heading level; G01 explicitly owns the route `h1`. Section, detail, and reviewer-control heading levels follow that choice, and the approved styling covers both heading hierarchies.

Final verification from the completed review-fix code:

```text
npm test -- src/components/gates/__tests__/GateReview.test.tsx src/components/__tests__/G01ReviewPanel.test.tsx
Test Files: 2 passed (2)
Tests: 59 passed (59)
Exit code: 0

npm run typecheck
tsc --noEmit
Exit code: 0

npm run lint
eslint .
Exit code: 0

git diff --check
Exit code: 0
Only expected LF-to-CRLF working-copy notices were emitted.

npm test
Test Files: 57 passed (57)
Tests: 418 passed (418)
Exit code: 0
Duration: 42.01s
```

Review-fix self-review found no open concern: stale evidence has no decision or run controls, recovered authority is exact-snapshot only, every decision candidate is validation- and binding-safe, no race can regress a newer terminal/version/history, the route retains exactly one `h1`, embedded reviews render none, dynamic heading styling is preserved, and the diff remains inside the Task 5 allowlist.
