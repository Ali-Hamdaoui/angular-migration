# Task 8 report: focus Transformation and actionable G07-G12 reviews

## Scope

Task 8 stayed within the approved frontend allowlist. The Transformation panel no longer owns transformation or command loading. `AuthoritativeRunDashboard` passes the shell-owned projection, projection status, executions, execution status, and both refresh callbacks into the current transformation stage.

The shared gate vocabulary now correctly presents:

- G11: **Repair validation acceptance**
- G12: **Stage-completion acceptance**

G11 and G12 approval controls remain unavailable unless the backend supplies both the exact active package checksum and workspace fingerprint. Submitted decisions retain the projection state version, package checksum, workspace fingerprint, generated idempotency key, and correlation ID. A successful decision refreshes both projections.

## Strict RED evidence

Before production edits, the new shell-owned-props, no-fetch, and G11/G12 action tests failed:

```text
Test Files: 1 failed
Tests: 3 failed, 16 passed
Failures: TransformationPanel still opened the transformation request and used the old G11/G12 labels.
```

## Focused GREEN evidence

```text
npm test -- --run src/components/__tests__/TransformationPanel.test.tsx
Test Files: 1 passed
Tests: 11 passed

npm test -- --run src/components/__tests__/TransformationPanel.test.tsx src/presentation/__tests__/gates.test.ts src/presentation/__tests__/currentAction.test.ts
Test Files: 3 passed
Tests: 57 passed

npm run typecheck
Exit code: 0

npm run lint
Exit code: 0 (one existing React exhaustive-deps warning was fixed in this task)

git diff --check
Exit code: 0
```

The full frontend suite was intentionally not run for this task. No backend files or API contracts changed.
