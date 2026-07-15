# Frontend

This workspace contains the Next.js Control Tower UI. It renders backend-owned
migration state only: it does not infer workflow transitions, execute migration
commands, mutate sandboxes, or approve gates without a backend request.

## AMF-S0-06 Control Tower shell

The Sprint 0 shell provides:

- `/migrations/new` for mock migration setup intent.
- `/migrations/[runId]` for the run dashboard.
- Setup, workflow, stage, agent, validation, approval, artifact, assistant, and
  report components.
- A static fixture shaped like the backend's `MigrationRunDto` response.

The fixture remains available only for explicit `mock-*` demo runs. Real run IDs
use the typed authoritative-run API and backend SSE stream; the browser never
owns workflow transitions or migration execution.

## ExecutionProfile review

The authoritative run dashboard includes the S1-F09 runtime review panel. It loads the persisted source-compatible Node/npm/npx resolution, displays exact versions and sanitized executable paths, requires backend-confirmed selection when multiple candidates exist, and renders blocked, stale, reconnecting, and failure states. The browser never executes commands or advances workflow state locally.
## API client

All frontend HTTP calls go through `src/api/client.ts`; endpoint-specific calls
live in `src/api/migrations.ts`. `NEXT_PUBLIC_BACKEND_URL` sets the backend base
URL and defaults to `http://127.0.0.1:8000`. Copy `.env.example` to `.env.local`
for a local override. The synchronized TypeScript contract types live in
`src/types/generated/api.ts`, with the backend OpenAPI document remaining the
source of truth.

The client exposes typed calls for `/health`, `/version`, `/environment/diagnostics`,
`/environment/refresh`, and the migration endpoints. No component calls `fetch()` directly. The run
dashboard (`/migrations/[runId]`) fetches backend-owned state through this
client and is rendered dynamically, so the backend must be running for live
data. `G01ReviewPanel` creates and starts a real run only after an approved
decision, then routes to its returned `run-*` ID.

## Server-Sent Events

Real run dashboards subscribe to `GET /api/v1/runs/{runId}/events` through the
`useAuthoritativeRun` hook (`src/hooks/useAuthoritativeRun.ts`). The hook opens
an `EventSource`, tracks connection status (`connecting`, `open`,
`reconnecting`, `closed`), and collects typed `MigrationEventDto` payloads.
The `applyEventToRun` reducer maps each event to the corresponding DTO fields
— stage status, agent status, validation gate, artifact, approval, or run
status — without inferring workflow transitions locally. A connection status
bar appears when the stream is not open, and a live event stream panel shows
received events. Refreshing the page reloads initial state from the backend
mock endpoint via server-side rendering.

## Run locally

```powershell
npm install
npm run dev
```

Open `http://localhost:3000/` to inspect Environment Diagnostics, then use
Refresh to capture the current machine snapshot. `/migrations/new` remains available
for mock migration setup. Check the shell with:

```powershell
npm test
npm run typecheck
npm run build
```

The backend contract vocabulary is documented in
[`shared/api-contracts.md`](../shared/api-contracts.md).
## Source and target path validation

On the setup page, Validate first canonicalizes the source and target through the
backend path authority. A blocked result must be resolved before preflight or
Start can proceed. Review the normalized paths, blocker codes, warnings, source
fingerprint, and reservation eligibility. The client never decides whether a
path is safe and never creates a target reservation locally.

Security-sensitive cases are fail-closed: network locations, source/target
overlap, internal-root access, disallowed roots, non-writable targets, and
uncertain symlink/reparse-point escapes are reported as blockers. Reservation
metadata expires and is persisted by the backend.

## Environment diagnostics manual check

1. Start the backend and frontend.
2. Open the Control Tower landing page and select **Refresh** under Environment Diagnostics.
3. Confirm Node, npm, npx, Git, and Python show only safe executable/version/root metadata.
4. Confirm storage, registry, proxy, HTTPS proxy, strict SSL, and custom-CA indicators show status only.
5. Verify a blocked result names an actionable blocker such as RUNTIME_PAIR_MISMATCH.
6. Confirm retrying a refresh with the same idempotency key returns the persisted snapshot without additional probes.

Credentials, proxy URLs, certificate contents, and other secret values must never be displayed or persisted.
