# Task 10 report: consolidate migration diagnostics

## Scope

Task 10 adds one Diagnostics workspace for the run's summary, current blocker, command executions and log artifacts, durable workflow events, governed LLM activity, and raw state. The workspace owns presentation only and receives existing authoritative/transformation state and refresh callbacks; it does not open another subscription.

Workflow events retain search, filters, and sequence ordering. Human labels lead each row, while raw event type, sequence, ID, stage, and payload remain under Technical details. LLM diagnostics lead with invocation outcome and affected operation; provider, model, token, cost, request, and payload metadata remain under Response details. Refresh is disabled while authoritative state is recovering or unavailable.

## Strict RED evidence

Before implementation, the new DiagnosticsWorkspace suite failed at module resolution because the workspace did not exist:

```text
Error: Failed to resolve import "../DiagnosticsWorkspace"
```

## Focused GREEN evidence

```text
npm test -- src/components/control-tower/__tests__/DiagnosticsWorkspace.test.tsx src/components/control-tower/__tests__/ControlTowerPresentation.test.tsx src/components/__tests__/LlmDiagnosticsPanel.test.tsx src/components/__tests__/AuthoritativeRunDashboard.test.tsx
Test Files: 4 passed
Tests: 67 passed

npm run typecheck
Exit code: 0

npm run lint
Exit code: 0

git diff --check
Exit code: 0
```

The full frontend suite was intentionally not run. No backend files or API contracts changed.

## Review fix round 1

The review fix prevents historical failure events from resurfacing as a current blocker after a completed transformation, searches event rows by both raw and humanized names, blocks governed LLM smoke actions while the authoritative connection is recovering, and keeps correlation/invocation identifiers inside Response details.

### Strict RED evidence

Before the fixes, the added review tests failed for historical blocker promotion and human-label event search:

```text
Test Files: 1 failed, 1 passed
Tests: 2 failed, 12 passed
```

### Focused GREEN evidence

```text
npm test -- src/components/control-tower/__tests__/DiagnosticsWorkspace.test.tsx src/components/control-tower/__tests__/ControlTowerPresentation.test.tsx src/components/__tests__/LlmDiagnosticsPanel.test.tsx src/components/__tests__/AuthoritativeRunDashboard.test.tsx
Test Files: 4 passed
Tests: 71 passed

npm run typecheck
Exit code: 0

npm run lint
Exit code: 0

git diff --check
Exit code: 0
```

The full frontend suite remains intentionally unrun.
