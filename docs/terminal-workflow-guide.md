# Terminal Workflow Guide (V2 F23)

This guide describes operating the ENTIRE migration lifecycle through the
terminal / API surface, from setup through stage execution to sealing and
delivery.  It extends the terminal operation guide (F06).

## Lifecycle phases

The full lifecycle is sequenced as:

```
setup → execution_profile → chain_start → stages → sealing → delivery
```

`GET /terminal/runs/{run_id}/lifecycle` returns the phase list, the current
phase, the durable chain status, stage progress, and the next permitted action.

## Driving the lifecycle

`POST /terminal/runs/{run_id}/lifecycle/drive` advances the lifecycle one
bounded step:

- `setup` → starts the durable stage chain (`POST /runs/{run}/chain/start`).
- `chain_start` / `stages` → advances the chain (`POST /runs/{run}/chain/advance`).
- `sealing` → advances; per-stage sealing happens via
  `POST /runs/{run}/stages/{stage}/validate` and `/seal`.

The `scripts/terminal-lifecycle.py` helper drives a bounded number of steps:

```
python3 scripts/terminal-lifecycle.py http://localhost:8000 run-1 --drive 3
```

## Lifecycle evidence

`GET /terminal/runs/{run_id}/lifecycle/evidence` returns the ordered workflow
events, the stage seals (immutable evidence freeze), and the next action.

## Full terminal lifecycle (setup → seal)

1. Create a run: `POST /runs`.
2. Resolve the execution profile: `POST /runs/{run}/execution-profiles/resolve`.
3. Start the chain: `POST /runs/{run}/chain/start`.
4. Advance stages: `POST /runs/{run}/chain/advance`.
5. On gate wait, approve: `POST /runs/{run}/approvals/G02/decisions`.
6. Validate and seal each stage: `POST /runs/{run}/stages/{stage}/validate`,
   `POST /runs/{run}/stages/{stage}/seal`.
7. Inspect lifecycle evidence: `GET /terminal/runs/{run}/lifecycle/evidence`.
8. Deliver the sealed workspace through the delivery service layer.

All operations are observable through the terminal; no frontend is required.
