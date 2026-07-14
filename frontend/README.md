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

The fixture is deliberately the only frontend data source in this issue. It has
no timers, status transitions, approval actions, or command behavior. AMF-S0-07
will replace it with a typed backend API client, and AMF-S0-08 will add SSE.

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
data; the static fixture remains available for tests.

## Server-Sent Events

The run dashboard subscribes to `GET /migrations/{runId}/events` through the
`useMigrationEvents` hook (`src/hooks/useMigrationEvents.ts`). The hook opens
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
## Environment diagnostics manual check

1. Start the backend and frontend.
2. Open the Control Tower landing page and select **Refresh** under Environment Diagnostics.
3. Confirm Node, npm, npx, Git, and Python show only safe executable/version/root metadata.
4. Confirm storage, registry, proxy, HTTPS proxy, strict SSL, and custom-CA indicators show status only.
5. Verify a blocked result names an actionable blocker such as RUNTIME_PAIR_MISMATCH.
6. Confirm retrying a refresh with the same idempotency key returns the persisted snapshot without additional probes.

Credentials, proxy URLs, certificate contents, and other secret values must never be displayed or persisted.
