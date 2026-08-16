# Terminal Operation Guide — Migration Factory (V2 F06)

This guide shows how a human operator drives a complete migration through the
terminal / HTTP API only, with no frontend.  All endpoints are exposed on the
unversioned surface and under `/api/v1`.

## 1. Get the next permitted action

```
GET /terminal/runs/{run_id}/next-action
```

Returns the workflow projection: run status, the next permitted action, the
remaining work, and the pending gate.

```
curl -s http://localhost:8000/terminal/runs/run-1/next-action
```

## 2. Inspect structured diagnostics

```
GET /terminal/runs/{run_id}/diagnostics
```

Composes the run's diagnostic packs (F03), failure groups and root causes
(F19) for terminal triage.

```
curl -s http://localhost:8000/terminal/runs/run-1/diagnostics
```

## 3. Resume the migration

```
POST /terminal/runs/{run_id}/resume
```

Resumes the durable stage chain (F12) and reports the next action.

```
curl -s -X POST http://localhost:8000/terminal/runs/run-1/resume -H 'Content-Type: application/json' -d '{"actor":"operator"}'
```

## 4. Approve a gate (governed approval actions)

The governed approval decisions live under `/runs/{run_id}/approvals/G0X/decisions`
(e.g. `G01` preflight, `G02` source intake, `G03` baseline, `G05` feasibility).
Submit the decision through the governing gate endpoint.

```
curl -s -X POST http://localhost:8000/runs/run-1/approvals/G01/decisions \
  -H 'Content-Type: application/json' \
  -d '{"decision":"APPROVED","actor":"operator","idempotency_key":"term-approve-1","expected_state_version":1}'
```

## 5. Full terminal lifecycle (setup → seal)

1. Create a run: `POST /runs` with the preflight + input checksums.
2. Resolve the execution profile: `POST /runs/{run}/execution-profiles/resolve`.
3. Start the chain: `POST /runs/{run}/chain/start`.
4. Advance/validate/seal stages: `POST /runs/{run}/chain/advance`,
   `POST /runs/{run}/stages/{stage}/validate`, `POST /runs/{run}/stages/{stage}/seal`.
5. On gate wait, approve: `POST /runs/{run}/approvals`.
6. On failure, diagnose and repair: `GET /terminal/runs/{run}/diagnostics`,
   `POST /runs/{run}/attempts/{attempt}/cycles` + `POST /cycles/{cycle}/decide`.
7. Deliver: after all stages seal, use the workspace delivery endpoint
   (the atomic delivery surface under the delivery router).
