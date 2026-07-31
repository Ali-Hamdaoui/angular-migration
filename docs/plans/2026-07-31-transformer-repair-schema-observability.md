# Plan — Transformer Repair: schema/response contract and failed-invocation observability

- Date: 2026-07-31
- Branch: fix/transformer-repair-llm-wiring
- BASE_SHA: 713f22126d32748a95a04dd639f0cddba291cfdf (user checkpoint)
- Run under investigation: run-6f89ac89792a (stage `angular-18-to-19--40f56dc556b22740`, attempt
  `repair-angular-18-to-19--40f56dc556b22740-1`, blocked at `propose_repair`,
  `LLM_SCHEMA_VALIDATION_FAILED` = "Provider response failed schema validation.")
- Mode: code-truth investigation + implementation; preserved control-tower DB is read-only by
  sqlite3 `mode=ro` only (never opened during this work).

## 1. Proven functional root cause

Classification: **D — Provider JSON versus local RepairProposal mismatch.**

The failure is raised **after transport, before any persistence**, at the only site producing the
observed message:

- `PromptSchemaRegistry.validate` — `backend/app/llm_gateway/azure_gateway.py:248-249`
  `StructuredOutputValidationError(LlmFailureCode.SCHEMA, 'Provider response failed schema
  validation.', failure_stage='schema_validation', failure_subtype='ASSISTANT_SCHEMA_VALIDATION')`
  chained from the Pydantic `ValidationError` via `from exc`.

Proof of mismatch (computed locally, no Azure):

1. `RepairProposal.model_json_schema()` (RAW) constrains model-invented vocabularies **only by
   `pattern`**:
   - `operations.items.operation` `^(replace_text|create_text_file|delete_text_file|dependency_change)$`
   - `proposal_format` `^(operations|unified_diff)$`
   - `risk_level` `^(low|medium|high)$`
   - (reviewer) `decision` `^(accept|request_changes|reject)$`
   plus bounds (`minItems`/`maxItems`/`minLength`/`maxLength`) that also carry the contract.
2. `_azure_strict_schema` (`azure_gateway.py:506-533`) strips every one of those keywords
   (`_AZURE_UNSUPPORTED_SCHEMA_KEYS` includes `pattern`, `minItems`, `maxItems`, `minLength`,
   `maxLength`, ...). The provider therefore receives bare `{"type":"string"}` for those fields.
3. The provider can emit any out-of-vocabulary value (e.g. `operation: "modify_file"`,
   `proposal_format: "diff"`, `risk_level: "critical"`, or an extra key such as `summary`); the
   Azure strict schema is satisfied, the request is HTTP 200, then the **local** Pydantic model
   rejects the payload → `LLM_SCHEMA_VALIDATION_FAILED`.
4. Analysis/Planning schemas do not exhibit this because their provider-visible fields carry no
   pattern-only constraints (`AnalysisGatewayNarrative`, `PlanningGatewayNarrative/Review`).

Checksums (SHA-256, computed locally in-process):

| Representation | wire order (insertion, as serialized at azure_gateway.py:294) | sort_keys=True |
| --- | --- | --- |
| RAW `RepairProposal.model_json_schema()` (== registered, zero transformation at `azure_gateway.py:236-239,257-261`) | `22da5ada649032003ecdae09c580bf159ee16ad6e05f1d0c42be5babc96e76d3` | `46a093c431aa9e33ccfc5a9052aba4cbd8fb8171dfac1034c9ceb3e5ed96ea2e` |
| AZURE-normalized (payload `text.format.schema`, `azure_gateway.py:491`) | `1f98c7887bc5995781b3f3d5d7885afa40a86a42007a0647b2f0a7c74161a7c0` | `9340eb62ba858c0f58ad28a017462ee48285bc320db49f91c23c6c1edf41cc26` |

Structural diff RAW → AZURE (per path):

```
REMOVED $defs/title/$schema; root required gains unified_diff (normalization forces all properties required)
REMOVED properties.operations.items.properties.operation.pattern
REMOVED properties.proposal_format.pattern
REMOVED properties.risk_level.pattern
REMOVED properties.operations.{maxItems}; operations.items.$ref inlined
REMOVED touched_files/rationale/validation_targets.{minItems,maxItems}; limitations.maxItems
REMOVED path.{minLength,maxLength}; unified_diff.{maxLength,default}
ADDED   operations.items.{additionalProperties:false, required:all 6 incl. nullable ones}
```

No `anyOf`/`oneOf`/`if-then-else` at root; 5 nullable `anyOf[..., null]` sites survive
(`unified_diff`, `preimage_sha256`, `old_text`, `new_text`, `content`) — provider accepted the
request (no 400 observed), so acceptance of `null`-in-`anyOf` is presumed; the diagnosis is the
vocabulary gap, not nullability.

Secondary proven defect (observability, same failed call): `RepairApplicationService` persists an
`LlmInvocationModel` row **only on success** (`_persist_call`,
`backend/app/services/repair_application_service.py:488-558`); its failure writer
(`_persist_deterministic_failure`, `:438-454`) is gated to
`_DETERMINISTIC_LOCAL_FAILURE_CODES = {LLM_PROMPT_POLICY_MISSING, LLM_SCHEMA_POLICY_MISSING,
LLM_CONFIGURATION_INVALID}` (`:83-87`), so a schema-validation failure persists **nothing** (no
invocation row, no usage, no provider request ID, no validation detail, no failure artifact). The
gateway additionally drops transport evidence for schema-validation failures: `_preserve_transport_evidence`
(`azure_gateway.py:477-488`) is invoked only for `_validate_response_state` failures
(`:431-437`), not for the `_registry.validate` call at `:438`. Analysis/Planning create the row
**before** transport and update it in place on failure
(`analysis_evidence_application_service.py:79-105,424-441`;
`planning_review_evidence_application_service.py:979-1012,1067-1083`); Repair diverges from that
established pattern.

## 2. Exact production call path

1. `TransformerOrchestrator.advance` dispatches `propose_repair` — `backend/app/orchestration/transformer_graph.py:167-168`
2. `_propose_repair` → `self._repairs.propose(attempt_id)` — `transformer_graph.py:935-941`
3. `propose()`: `_attempt_context` (:193) → `_recover_completed` (:194) → `_call` (:197-207) → `validate_proposal` (:208) → `_write` (:209) → `_persist_call` (:210)
4. `_call`: registry register (:358-359) → gateway construction (:361) → `gateway.complete` (:362-384) → `registry.validate` (:385)
5. `complete()`: prompt lookup (`azure_gateway.py:411-416`) → payload with `text.format.schema` = `_azure_strict_schema(RepairProposal.model_json_schema())` (`:491`, `:257-261`) → transport (`:428`, `UrllibAzureTransport.request` `:291-346`) → `_validate_response_state` (`:431-437`) → `_registry.validate` (**failure site**, `:438` → `:248-249`) → usage/budget (`:439-443`)
6. `_translate_gateway_failure` (`repair_application_service.py:104-130`) maps `SCHEMA` → `LLM_SCHEMA_VALIDATION_FAILED` (`:72`); not in `_DETERMINISTIC_LOCAL_FAILURE_CODES` → re-raise with zero persistence (`:386-390`)
7. Graph `_block` persists `last_error_code`/`last_error_message`, releases lease (`transformer_graph.py:1396-1403`); blocked continuations are never reclaimed (`claim_next` selects only QUEUED/CANCELLING/expired-RUNNING — `transformation_continuation_service.py:150-200`).

## 3. Required invariants (unchanged or strengthened)

1. Strict structured output only; **no JSON-mode fallback**, no permissive dict schema, no silent
   coercion/markdown stripping.
2. Repair authority preserved: only the Proposer authors candidate content; the Reviewer cannot
   author/replace/edit a diff (`RepairReview` `extra="forbid"` + registered prompt policy);
   no command execution, gate approval, automatic application, or workflow-state mutation by the LLM.
3. Provider schema satisfies the supported strict subset recursively: root object, all properties
   required, `additionalProperties=false`, no unsupported keywords, deterministic order, bounded
   depth/property count.
4. Local semantic validation (`validate_proposal`, `repair_application_service.py:236-309`)
   remains authoritative and unchanged: `operations` format ⇒ non-empty operations and
   `unified_diff is None`; `unified_diff` format ⇒ empty operations and non-empty diff; stale
   evidence bindings, preimage checks, path policy all enforced after Pydantic validation.
5. Proposal artifact registered only after a valid `RepairProposal`; reviewer cannot run without a
   valid proposal (`_attempt_context(include_proposal=True)` → `REPAIR_PROPOSAL_MISSING`).
6. Exactly one logical invocation per (RepairAttempt, role) — unique key
   `uq_llm_invocations_run_idempotency` on `(run_id, idempotency_key)`
   (`repositories/models/workflow.py:710`); `idempotency_key = f"{attempt.id}:{role}"`.
7. Provider request ID is truthful and immutable once known; never fabricated.
8. No raw provider output, API keys, headers, complete prompts, or unredacted source persisted.
9. Blocked continuations stay non-claimable; lease is released on block (existing graph behavior).
10. Analysis/Planning structured-output and evidence behavior remain compatible.

## 4. Transaction design

- **Txn A (start):** insert/obtain invocation row `status="in_progress"`,
  `transport_started=False`, `idempotency_key=f"{attempt.id}:{role}"` → commit. No network inside.
- **External work:** gateway call with no open DB session (already true).
- **Txn B (outcome):** update the same row — success: `status="completed"`, transport/response
  fields, usage record (same scope, `usage_cost_records.invocation_id` UNIQUE), artifact metadata,
  attempt fields; failure: `status="failed"`, `failure_code`, `failure_stage`/`failure_subtype`,
  provider/response fields as carried by the gateway error, retries, `completed_at`. Crash between
  A and B leaves an `in_progress` row that `_recover_completed` resolves safely (below).

## 5. Safe diagnostic contract

Persist only bounded, sanitized values (all existing columns, no migration):

- identity/status: `id`, `run_id`, `stage_id`, `idempotency_key`, `status`, `role`, `task_type`,
  `stage="repair"`, `actor="transformer"`
- versions/checksums: `prompt_version`, `schema_version`; schema checksum folded into
  `input_hashes` as `f"schema:{sha256(json.dumps(raw_schema, sort_keys=True))}"` (no column
  exists; adding a column is not justified — `input_hashes` is a JSON list already carrying
  evidence checksums)
- transport: `transport_started`, `response_received`, `provider_http_status`,
  `provider_request_id` (only when the gateway error carries it), `response_content_type`,
  `response_bytes`, `response_sha256`, `response_kind`, `retries`, `retryable`,
  `transport_exception_type`, `endpoint_host`, `endpoint_path`
- failure: `failure_code`, `failure_stage` (reuse gateway taxonomy: `http_request`,
  `http_response`, `response_body_read`, `response_json_decode`, `schema_validation`,
  plus `repair_semantics` for post-transport `RepairApplicationError`), `failure_subtype`
  (`ASSISTANT_SCHEMA_VALIDATION`, `REFUSAL_OR_INCOMPLETE_RESPONSE`, `INVALID_JSON`,
  `MISSING_OUTPUT`, ...), `provider_error_code`, `sanitized_provider_message`
  (bounded ≤240 chars, redacted)
- validation detail: bounded locations/types only (e.g. `loc` path segments and error `type` for
  the first few Pydantic errors, total ≤240 chars) — never values
- failure artifact (`propose-error.json`/`review-error.json`): same bounded field set, plus
  `response_received`, `transport_started`, `response_sha256`, `response_bytes`, `response_kind`,
  `provider_error_code`, `sanitized_provider_message`, `provider_http_status`, `retries`
- never: raw provider output, complete prompts, API keys, authorization headers, unredacted
  source or repository content

## 6. Exactly-once invocation identity

- Identity: `(run_id, idempotency_key)` with `idempotency_key = f"{attempt.id}:{role}"`,
  role ∈ `repair_proposer | repair_reviewer` (matches current `_recover_completed` and
  `_persist_call` usage).
- Success replay: row `completed` → replay artifact, no second provider call (existing
  `_recover_completed` behavior, keep).
- Failure replay (operator-resumed blocked run after corrected deployment): row `failed` →
  retry allowed, same row updated (`retries+1`), `provider_request_id` write-once.
- Crash window: row `in_progress` and `transport_started` falsy → safe retry, same row;
  `in_progress` and `transport_started` truthy → block `REPAIR_INVOCATION_UNCERTAIN`
  (cannot prove no provider side effect — fail closed).
- Usage record only on success (usage genuinely unavailable on failure).
- Proposal artifact only after valid `RepairProposal`; reviewer impossible without proposal.

## 7. Files and symbols to change

Implementation Agent 1 (schema/response):
- `backend/app/services/repair_application_service.py` — `RepairOperation.operation`,
  `RepairProposal.proposal_format`, `RepairProposal.risk_level`, `RepairReview.decision`:
  convert `str` + `pattern` to `Literal[...]` (identical allowed values; `enum` survives
  `_azure_strict_schema` — verified; this strengthens the provider contract, never weakens local
  validation). No other model change.
- `backend/app/llm_gateway/azure_gateway.py`:
  - `PromptSchemaRegistry.validate` (`:241-255`): attach bounded validation detail
    (locations/types only) to `provider_message` and set `provider_code='schema_validation'`
    on the `StructuredOutputValidationError`.
  - `AzureOpenAILLMGateway.complete` (`:438`): wrap `self._registry.validate(...)` so
    `_preserve_transport_evidence` (provider request ID, status, response sha/bytes/kind,
    `transport_started=True`, `response_received=True`) is applied to the schema-validation
    error before re-raise.
  - `PromptRegistry.defaults()` repair prompts (`:134-135`): enumerate the three vocabularies
    and the `operations` XOR `unified_diff` format rule so the provider is instructed with the
    exact contract (complement, not substitute, for the schema enum).
- `backend/app/services/repair_application_service.py` — `validate_proposal` and refusal/
  incomplete/empty/invalid-JSON classification stay as-is (already distinct PROTOCOL handling
  in the gateway).

Implementation Agent 2 (failed-invocation observability):
- `backend/app/services/repair_application_service.py`:
  - `propose()`/`review()`: after `_recover_completed` returns None, `_start_invocation(context,
    role, task, schema_name, schema)` — Txn A insert-or-get by idempotency key.
  - `_persist_call` (`:488-558`): update the pre-created row instead of inserting a fresh one
    (same scope: usage record, artifact metadata, attempt fields).
  - `_persist_deterministic_failure` (`:438-454`): generalize to `_persist_failure` — write the
    bounded failure artifact for **all** failure codes and update the same invocation row in one
    Txn B scope.
  - `_call` (`:353-390`): on `AzureGatewayError` → translate → `_persist_failure` (all codes) →
    raise.
  - `propose()`/`review()`: post-transport `RepairApplicationError` (semantic) and
    `ValidationError` paths → `_persist_failure` (stage `repair_semantics`) → raise.
  - `_recover_completed` (`:392-436`): add `failed` → retry-ok, `in_progress` +
    falsy `transport_started` → retry-ok, `in_progress` + truthy `transport_started` →
    `REPAIR_INVOCATION_UNCERTAIN`.
- `backend/app/llm_gateway/azure_gateway.py`: only the pieces listed for Agent 1 (transport
  evidence on schema errors) — single gateway change shared by both agents, owned by Agent 1.

## 8. Focused tests

- `backend/tests/test_repair_provider_schema_policy.py` (new, mirrors
  `test_analysis_provider_schema_policy.py`): repair schemas azure-strict walk (no unsupported
  keys; every object `additionalProperties=false`; `required == properties`); enum present for
  `operation`/`proposal_format`/`risk_level`/`decision`; RAW/AZURE checksums stable; no
  speculative weakening.
- `backend/tests/test_llm_gateway.py`: extend schema-mismatch test — transport evidence
  (`provider_request_id`, `response_sha256`, `transport_started=True`, `response_received=True`)
  preserved on `StructuredOutputValidationError`; bounded validation detail present; refusal /
  incomplete / empty / invalid JSON / semantic remain distinct (existing tests kept).
- `backend/tests/test_repair_application_service.py`: invocation lifecycle — row exists before
  transport; pre-transport failure (`transport_started=False`); schema failure updates row with
  transport fields; semantic failure stage; no fabricated request ID; replay updates same row;
  reviewer failure row.
- `backend/tests/test_transformer_repair_failure_governance.py`: invert `LlmInvocationModel
  count()==0` assertions (lines 495, 583, 639, 748, 785) to exactly one failed row with safe
  fields; add schema-validation-failure governance case (`LLM_SCHEMA_VALIDATION_FAILED` with
  provider-request-id preserved); failed reviewer; failure replay (no duplicate row, no duplicate
  logical invocation); `REPAIR_EVIDENCE_MISSING` keeps zero rows (fails before invocation
  creation); success replay unchanged (1 row, 1 usage, 1 call).
- Regression: `test_analysis_provider_schema_policy.py`, analysis/planning evidence tests
  (scoped).

## 9. Current-run recovery implications

- The preserved control-tower DB, frozen evidence, checkpoint, RepairAttempt, G06/G07 are not
  touched. No migration is added (all evidence fields exist on `llm_invocations`).
- After deployment, the operator explicitly resumes run-6f89ac89792a (blocked continuation is
  not reclaimable by workers): `propose_repair` re-enters, `_recover_completed` finds no
  completed invocation, a single `in_progress` invocation row is created for
  `repair-angular-18-to-19--40f56dc556b22740-1:repair_proposer`, and the provider is called once
  with the corrected schema. Success or failure is now durable; failure blocks again with full
  diagnostics; success proceeds to `review_repair` → G10.

## 10. Out of scope

- Angular command templates, Angular update command, Jest dependency, peer-dependency failure,
  stage plan, compatibility catalogue, RepairAttempt model, G06, G07.
- Waking/restarting run-6f89ac89792a, opening the preserved DB in write mode, running full
  backend/frontend suites, real Azure requests, Alembic migrations (none needed).
- `frontend/next-env.d.ts` (user-owned, untouched).
