# MT-003 browser evidence — S3-F03

Run date: 2026-07-20 (local browser run, production Next server on `127.0.0.1:3302`)

## Scenario result

The browser executed the registered `python-stream` command through S3-F01 authorization and S3-F02 execution. The selected successful execution was `exec-9b8ba5d49aa6`, with correlation ID `ec1de91a-be14-4188-a53e-302312399fb2`, duration `8778 ms`, exit code `0`, and status `succeeded`.

- The UI displayed the live-output pause control while the command was running; clicking it changed the control to Play, then Play resumed consumption without cancelling the execution.
- The browser refreshed and reconnected to the same durable execution. The viewer opened backend-origin SSE URLs, including `.../logs/stream?cursor=0`; no frontend-origin `/api` request was used.
- Durable log persistence contains one stdout chunk, sequence `1`, 243 bytes, with all twelve `MT-003 live line` records and `truncated=false`. The final artifact set contains five immutable artifacts; the output artifact checksum is `sha256:a8ee21e68936a4c92a5fcb4bea2885be00c2a84a6857885be0ec0c1b39603d6c`.
- Durable event order for the successful execution is `COMMAND_QUEUED` (#26), `COMMAND_STARTED` (#27), `COMMAND_OUTPUT_AVAILABLE` (#28), `COMMAND_SUCCEEDED` (#29). Earlier setup attempts are retained as failed executions and are not part of the successful evidence.
- The isolated workspace source hash remained `SHA256 0FEF591F57E4E67D244A8665594E0A1DF2136FFA351B6E52D759C50D3D0BE270` before and after execution.

## Captured screenshots

- [01-initial.png](mt003-evidence/01-initial.png)
- [02-authorized.png](mt003-evidence/02-authorized.png)
- [03-running.png](mt003-evidence/03-running.png)
- [04-paused.png](mt003-evidence/04-paused.png)
- [05-reconnected.png](mt003-evidence/05-reconnected.png)

## Negative and security checks

- Cross-actor command listing returned `403` with stable `RUN_ACCESS_FORBIDDEN`.
- Unsupported `stream=debug` returned `422` with stable `INVALID_LOG_STREAM` and the allowed stream list.
- Artifact and SSE URLs used `http://127.0.0.1:8000` as the backend origin, matching the API client configuration.
