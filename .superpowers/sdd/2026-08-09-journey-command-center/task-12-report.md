# Task 12 report: unified landing, routes, mock compatibility, and shell styling

## Scope

Task 12 now presents a plain-language landing page with clear Start a new migration and Resume active migration actions. Preparation guidance explains the four-step journey and keeps environment details behind View diagnostics. Restoration behavior and `ACTIVE_RUN_STORAGE_KEY` are unchanged.

Mock migration data enters the shared legacy dashboard shell through an explicit non-authoritative mode. Mock runs display an explicit notice and do not open authoritative event streams or mutation controls. The legacy shell exposes the same four primary destinations as the authoritative shell: Overview, Pipeline, Evidence, and Diagnostics.

Touched shell and route content has no mojibake or text-symbol icons. Landing, mock notice, and legacy navigation styles are owned by the shared global/module styles already used by these surfaces.

## Strict RED evidence

The new landing, mock-route notice, and four-destination assertions failed before implementation:

```text
Test Files: 3 failed
Tests: 4 failed, 5 passed
```

Failures covered the old Control Tower landing hierarchy, missing mock non-authoritative notice, and missing navigation on the legacy shell.

## Focused GREEN evidence

```text
npm test -- --run src/app/__tests__/page.test.tsx src/app/__tests__/migrationRunPage.test.tsx src/components/__tests__/ControlTowerShell.test.tsx
Test Files: 3 passed
Tests: 9 passed

npm run typecheck
Exit code: 0

npm run lint
Exit code: 0

git diff --check
Exit code: 0
```

The full frontend suite was intentionally not run. No backend files or API contracts changed.

## Review fix round 1

The legacy shell navigation is now a real anchored destination set with selected state and `aria-current="page"` for Overview, Pipeline, Evidence, and Diagnostics. Mock runs use an explicit `mode="mock"` path that renders the legacy shell without SSE, authoritative package loading, gate controls, or mutation panels; the mock notice remains visible and no synthetic preflight, workspace, or state identifiers are created. Landing restoration keeps Resume active migration conditional: it is hidden without a valid candidate and uses the encoded candidate only when one is available. Mock and authoritative route failures now show a truthful retry/return surface.

Strict RED evidence for the review fixes:

```text
Test Files: 3 failed
Tests: 5 failed, 6 passed
```

Focused GREEN evidence:

```text
npm test -- --run src/app/__tests__/page.test.tsx src/app/__tests__/migrationRunPage.test.tsx src/components/__tests__/ControlTowerShell.test.tsx
Test Files: 3 passed
Tests: 11 passed

npm run typecheck
Exit code: 0

npm run lint
Exit code: 0

git diff --check
Exit code: 0
```

The full frontend suite remains intentionally unrun.
