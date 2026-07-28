# AMFA-221 Assistant closure slice

## Shared authority path

Persisted `migration_runs`, stages, steps, command executions, LLM invocation and
usage records, workflow events, and immutable artifact metadata are composed by
`WorkflowProjectionService`. The projection is exposed as
`AuthoritativeRunStateDto.assistant_projection` through
`MigrationRunService.get_state`. The production path is
`AssistantContextService → LlmEvidenceApplicationService.assistant() → the
existing governed role router/gateway`; the isolated demo injects a fake only
at the supported external provider seam. The Assistant must consume this projection;
raw event names and artifact filenames are not semantic authority.

## Supported and unavailable fields

Known values are represented by `ProjectionValue(availability="known")`.
Missing values are `unavailable`; fields not represented by the current
workflow contract are `unsupported`. Run and Angular versions, phase/status,
stage and step records, repair state, artifacts, command totals, and persisted
LLM usage are supported where records exist. Typed next-action, blocker,
waiting/failure reason, stage fingerprint, package-manager profile, and full
phase-duration boundaries remain unavailable until their owning workflow
contracts expose them.

## Statistics formulas

- Terminal workflow duration is `updated_at - created_at` for terminal runs.
- Active-run age is calculated only for a live request from persisted
  `created_at` and the controlled service clock.
- Stage duration is `completed_at - started_at` when both persisted boundaries
  exist; missing boundaries are omitted.
- Command totals count persisted command executions by status. Retries remain
  separate executions when separate rows exist.
- LLM totals include completed usage rows joined to completed invocations and
  are grouped by persisted invocation role. No authoritative rows produce
  `null`/unavailable values; a persisted zero-valued usage row produces zero.
  An invocation without a persisted usage row remains unavailable, never zero;
  the UI preserves unavailable token and cost values.

## Assistant and evidence behavior

For persisted authoritative runs, `AssistantContextService` consumes
`MigrationRunService.get_state().assistant_projection`; the old event/file-name
projection is bypassed on that path. Normal state questions call
`LlmEvidenceApplicationService.assistant()`, which resolves the Assistant role
through the existing S2-F03 governed gateway path. Structured answers, state
version, and citations are validated before Assistant persistence.

The S2-F03 service owns provider invocation, budget blocking, retry/timeout and
structured-response classification, invocation provenance, and provider usage.
The Assistant service owns Assistant lifecycle events, conversation/message
ordering, citations, proof labels, and stale semantics. Each exchange persists
one ordered `user` row followed by one ordered `assistant` row; terminal
failures persist the user row and a failed Assistant row without fabricating a
completed answer. Assistant messages remain run-scoped, ordered, bounded,
idempotent, and carry the workflow state version used to answer. Historical
rows are not rewritten;
GET marks an older answer stale against the current projection version. Reuse
of an idempotency key with a changed checksum is rejected; the checksum covers
`message`, `conversation_id`, and `client_known_state_version`. Started,
completed, and recoverable failed lifecycle events are persisted.

Evidence is selected from run-owned immutable artifact metadata referenced by
typed workflow evidence IDs and retains checksum/run/stage information. A
citation must also have an approved status, supported evidence type, immutable
metadata, matching run/checksum, and either a stage whose persisted owner is
the current run or explicit run lineage. Missing, wrong-run,
checksum-mismatched, unapproved, rejected, superseded, unsupported, or
unowned evidence is rejected. Filename
substring matching is not used by the shared projection.

## Frontend ownership and recovery

Run restoration remains owned by the page/root (`/?run_id`,
`amfa.activeRunId`). `AssistantPanel` owns only conversation display and its
named lifecycle SSE listeners; sequence gaps trigger persisted history reload.
The SSE endpoint replays only lifecycle rows with sequence greater than the
`Last-Event-ID` cursor, so reconnecting does not duplicate messages, lifecycle
events, invocations, usage, or cost.

## Validation and limitations

Executable isolated demonstration command:

```powershell
cd C:\Users\ilyas.abarbach\Documents\angular-migration\backend
.\.venv\Scripts\python.exe -m pytest tests/test_amfa221_vertical_demo.py -q
```

Observed result: `1 passed, 2 warnings` (timing varies). The test uses an isolated
temporary SQLite database plus temporary artifact/output roots; no repository
database or production artifact root is used. The remaining limitation is
that unsupported workflow fields remain unavailable, and no real Azure
credential proof is claimed. Focused validation passed: backend closure,
regression, and system tests `49 passed, 5 warnings`; Ruff and compileall
passed; frontend typecheck and AssistantPanel test passed; frontend lint has
only the unchanged `AuthoritativeRunDashboard.tsx` hook warning. The known
unrelated MigrationSetupForm port-baseline failure was not part of this slice.
