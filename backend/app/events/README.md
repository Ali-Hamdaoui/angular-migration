# Events

Owns ordered workflow event persistence, replay, heartbeat coordination, and SSE
delivery helpers.

Events are delivery evidence, not the authoritative workflow state. This module
must not decide state transitions, execute commands, mutate workspaces, or let
the frontend invent progress.

## SSE Format

`GET /migrations/{run_id}/events` streams `text/event-stream` frames. Workflow
events include:

```text
id: 7
event: stage_state_changed
data: {"event_id":"evt-stage-committed","run_id":"mock-run","sequence":7,...}
```

The `id` is the run-scoped monotonic event sequence. The browser uses it as
`Last-Event-ID` on reconnect. The server replays retained events with sequence
values greater than the supplied ID. If the requested range is no longer
retained, the stream emits:

```text
event: replay_unavailable
data: {"recovery":"snapshot_required",...}
```

Idle streams emit `heartbeat` frames. The frontend ignores duplicate or older
sequences, detects sequence gaps, and refreshes the authoritative state snapshot
when replay is unavailable or a gap appears.

## Local Replay Demo

```bash
curl -N http://127.0.0.1:8000/migrations/mock-run-angular-18-to-21/events
curl -N -H "Last-Event-ID: 7" http://127.0.0.1:8000/migrations/mock-run-angular-18-to-21/events
```
