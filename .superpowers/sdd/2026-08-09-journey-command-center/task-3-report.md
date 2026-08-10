# Task 3 report: accessible visual foundation

## Files changed

- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/src/app/globals.css`
- `frontend/src/components/StatusPill.tsx`
- `frontend/src/components/control-tower/TechnicalDetails.tsx`
- `frontend/src/components/control-tower/ControlTowerLayout.module.css`
- `frontend/src/components/ControlTowerShell.module.css`
- `frontend/src/components/control-tower/__tests__/ControlTowerPresentation.test.tsx`
- `frontend/src/components/__tests__/ControlTowerShell.test.tsx` (single test-only scope amendment authorized after the full-suite RED)
- `.superpowers/sdd/2026-08-09-journey-command-center/task-3-report.md`

## RED evidence

1. After adding the Task 3 tests first, `npm test -- src/components/control-tower/__tests__/ControlTowerPresentation.test.tsx` failed with exit 1 because `../TechnicalDetails` did not exist. Vitest reported 1 failed test file and 0 loaded tests.
2. After adding only a compileable disclosure scaffold, the same focused command failed for the intended missing behavior: 6 failed and 2 passed. The three `status`-prop cases crashed in the legacy `value.replaceAll` implementation, the legacy value case still exposed `WAITING APPROVAL`, closed technical content was visible, and no native `<details open>` state existed.
3. The first complete `npm test` run exposed one stale migration assertion: 1 failed and 307 passed across 55 files. `ControlTowerShell.test.tsx` expected raw `WAITING` twice, while the new legacy `value` call correctly used `presentStatus` and rendered `Waiting`. The root agent authorized a one-file, test-only scope amendment. The amended test now verifies one human `Waiting` presentation, independently preserved raw `WAITING` evidence, and the sentence-cased `Manual validation required` presentation. Production output was not weakened to satisfy the old assertion.

## Implementation summary

- Installed exact `lucide-react@1.31.0` and used Lucide icons for all new status/disclosure iconography.
- Added the exact approved color, focus-ring, and spacing tokens to `:root`, the `Segoe UI`-headed local system stack, 16 px/1.5 body defaults, 44 px minimum pointer height, technical-value wrapping, visible focus, and the specified reduced-motion defaults.
- Removed gradients, colored glow/glass effects, duplicated foundation blocks, undersized supporting text touched by this task, and duplicate Assistant presentation selectors from the two shared CSS files. Shared foundation rules now use flat approved token colors.
- `StatusPill` now has a type-safe mutually exclusive `status`/legacy `value` prop contract. It accepts `StatusPresentation` directly, passes ordinary raw strings through `presentStatus`, and composes only valid `Gxx_CREATED` values through `isGateId`/`gateDefinition`. `G11_CREATED` renders `Repair validation acceptance required` with warning tone. Unknown values remain neutral; tone is exposed through `data-tone`; icons are decorative with adjacent visible labels.
- `TechnicalDetails` is a native `<details>`/`<summary>` disclosure, closed unless its optional native `open` prop is supplied. It has no open-state handler, uses Lucide settings/chevron icons, and wraps long code, preformatted content, and identifiers within its own region.
- No fetch, mutation, timer, inferred progress, percentage, route, backend contract, or later command-center flow was added.

## Verification output

### Focused Task 3 component suite

Command: `npm test -- src/components/control-tower/__tests__/ControlTowerPresentation.test.tsx`

```text
Test Files  1 passed (1)
Tests       8 passed (8)
Exit code: 0
```

### Authorized legacy-shell compatibility test

Command: `npm test -- src/components/__tests__/ControlTowerShell.test.tsx`

```text
Test Files  1 passed (1)
Tests       1 passed (1)
Exit code: 0
```

### Typecheck

Command: `npm run typecheck`

```text
> tsc --noEmit
Exit code: 0
```

### Lint

Command: `npm run lint`

```text
> eslint .
Exit code: 0
```

### Diff integrity

Command: `git diff --check`

```text
Exit code: 0
```

Git emitted only Windows LF-to-CRLF conversion notices; it reported no whitespace errors.

### Complete frontend suite

Command: `npm test`

```text
Test Files  55 passed (55)
Tests       308 passed (308)
Exit code: 0
```

## Dependency-diff confirmation

- `npm ls lucide-react --depth=0` reports exactly `lucide-react@1.31.0`.
- `frontend/package.json` adds only `"lucide-react": "1.31.0"`.
- The lockfile contains the matching `1.31.0` package, registry URL, integrity, and React peer range.
- No unrelated package version was upgraded. The local Windows npm rewrite adjusted peer/optional metadata and removed the unused optional `@emnapi/core` and `@emnapi/runtime` lock entries; all focused/static/full verification passed afterward.
- `npm install` reported 7 high-severity audit findings. This task did not run `npm audit fix` because dependency remediation would be unrelated scope and could upgrade packages.

## Self-review

- Approved image: re-inspected at native resolution before implementation and during final review. The foundation matches its flat near-black/navy surfaces, cyan accent, green success, amber action/warning, red danger, thin borders, compact 10 px rounded rows/panels, icon-plus-label status language, and collapsed technical-details pattern. Task 3 intentionally does not rebuild the pictured shell or flows.
- Scope: only Task 3 files plus the explicitly authorized one-test amendment and this report changed. No later setup, shell navigation, gate review, drawer, or product flow was pre-implemented.
- Keyboard/accessibility: disclosures retain native keyboard behavior; status meaning is icon plus visible text and never color-only; decorative icons are `aria-hidden`; global focus and 44 px target defaults are present; supporting text touched here is at least 13 px.
- Status authority: direct presentations are preserved; valid created gates use the authoritative G01-G12 vocabulary; unknown raw values are neutral and never inferred from success/failure substrings; legacy call sites remain type-safe and human-readable.
- Technical values: code/pre/identifier content uses `overflow-wrap: anywhere`, `white-space: pre-wrap`, and `word-break: break-word` inside a constrained region.
- Visual hygiene: static search found no gradients, backdrop filters, colored glow declarations, mojibake, or text-glyph icon markup in the Task 3 foundation files. New colors are the approved tokens; foundation token declarations occur once.
- React review: components are small and stateless, import no data/runtime machinery, create no effects, and use a module-level icon map instead of render-time component definitions.
- Mutation review: removing the gate-created branch breaks the G11 label/tone test; bypassing `presentStatus` breaks the legacy/unknown tests; exposing icon semantics breaks the decorative-icon test; replacing native details or defaulting it open breaks the disclosure tests.

## Concerns

- Browser screenshot comparison is intentionally deferred: Task 3 creates shared primitives and tokens but does not compose the final approved screen, and the plan reserves rendered browser QA for Task 13. The approved reference was reviewed directly and the foundation was checked against it without inventing the later shell.
- The npm audit findings and platform-specific lockfile metadata churn are documented above; neither caused a test, type, lint, or diff failure.

## Fix round 1

### Review findings and RED evidence

- Independent re-review found that the Windows-generated lockfile had removed baseline libc constraints and `@emnapi/core` / `@emnapi/runtime` records, while WASI packages still referenced that metadata. The lockfile was restored exactly from pre-Task-3 baseline `f1a6d663f4487b4f7e67296016124cd5b0aa1058` before the Lucide-only delta was reapplied. This supersedes the earlier acceptance of platform-specific lock churn above.
- Four focused regression contracts were added before the fix. `npm test -- src/components/control-tower/__tests__/ControlTowerPresentation.test.tsx` initially reported 4 failed and 8 passed: no rendered Lucide navigation icons, no explicit authoritative connection-state colors, no default-hidden/below-768 drawer contract, and no real 44 px wrapping box for anchors.

### Implementation

- Replaced the Header menu, source-to-target separator, connection marker, Sidebar close control, live marker, and all eleven navigation glyph strings with named `lucide-react` components. Every inserted SVG is decorative; visible button and navigation labels remain their accessible names, and navigation keys/callback behavior are unchanged.
- The connection base is now neutral. `open` alone uses success; `loading`, `connecting`, `reconnecting`, and `recovering` use warning; `failed` uses danger.
- Drawer controls are globally hidden by default and displayed only at `max-width: 767px`. The fixed-sidebar-to-drawer transition now covers 681–767 px, the local mobile layout declarations share that breakpoint, the two shell mobile blocks were consolidated, and the globally scoped 420 px summary rules occur after the 767 px rules so their overrides win.
- `a[href]` is an inline-flex, vertically aligned 44 px interaction box with constrained width and anywhere wrapping. Shared action links retain wrapping and avoid horizontal overflow.

### Verification

- Focused Task 3 suite after the fix: 1 file passed, 12 tests passed.
- Combined focused presentation and legacy-shell suites: 2 files passed, 13 tests passed.
- `npm run typecheck`: exit 0.
- `npm run lint`: exit 0.
- `git diff --check`: exit 0 (only Git's Windows LF-to-CRLF notices).
- `npm ls lucide-react --depth=0`: exactly `lucide-react@1.31.0`.
- `git diff f1a6d663f4487b4f7e67296016124cd5b0aa1058 -- frontend/package-lock.json`: exactly 10 added lines, comprising the root `lucide-react` dependency and its exact 1.31.0 package record; no baseline lock metadata removals or unrelated churn remain.
- The requested first full suite run reported 54 files passed and 1 failed; 311 tests passed and 1 failed. The only failure was the existing `AssistantPanel` 503 retry timing test, which found the error alert before the asynchronous Retry control rendered. An immediate isolated run of that exact test passed (1 passed, 7 skipped), showing that it is timing-sensitive under full-suite concurrency. No out-of-scope Assistant production or test file was changed.
- The parent authorized exactly one additional complete run on the unchanged tree. It reported 53 files passed and 2 failed; 310 tests passed and 2 failed. The same `AssistantPanel` retry failure recurred, and the existing `MigrationPlanPanel` tab test also synchronously queried Builder content before its state update rendered. Per the checkpoint instruction, no further run or commit was made.

### Self-review

- Static glyph/mojibake search is empty for the changed Header and Sidebar. The focused render asserts more than twelve SVGs, all `aria-hidden="true"` and without an image role, while preserving stable control classes and visible accessible names.
- The CSS state contract covers every member of `AuthoritativeConnectionStatus`; no non-open state inherits success.
- Mobile media declarations are ordered 900 px, 767 px, then 420 px. The 420 px metric and summary overrides therefore remain effective, and shell mobile declarations occur in one non-conflicting block.
- The lock proof is based on the pre-Task-3 baseline, not the reviewed commit, so the restored optional/peer metadata is included in the comparison.

### Concerns

- Full-suite concurrency remains a release blocker outside Task 3 scope: the `AssistantPanel` retry failure recurred in both complete runs even though its exact isolated test is green, and the authorized repeat also exposed a separate `MigrationPlanPanel` tab timing failure. Fix round 1 is intentionally uncommitted pending root direction.

### Post-stabilization verification

- Stabilization commits `b34af81` and `4235ac5` were present before verification. On that HEAD plus the unchanged Task 3 diff, the focused presentation/compatibility run passed 13/13 tests, typecheck and full lint exited 0, and the complete frontend suite passed 55/55 files and 316/316 tests.
- The earlier full-suite timing concern is resolved by those independently reviewed stabilization commits; Task 3 does not include their files.
- Five-finding self-review: the lock diff against `f1a6d66` is still exactly 10 Lucide-only additions with `npm ls` resolving 1.31.0; connection states use success only for `open`; Header/Sidebar glyphs are named decorative Lucide icons with desktop-hidden drawer controls; the 900/767/420 responsive cascade closes the 681–767 gap and keeps the global summary override effective; and interactive links use a wrapping, constrained inline-flex box with a 44 px minimum height.
