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
